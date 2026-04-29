"""
ERA-500 UDP Daemon
Слушает порт 7714, принимает пакеты от контроллеров,
парсит события прохода и пишет в БД + рассылает по WebSocket.
"""
import asyncio
import socket
import struct
import logging
import datetime
from database import db_add_event, db_get_employee_by_card, db_update_controller_status
from ws_manager import ws_manager

logger = logging.getLogger(__name__)

UDP_PORT = 7714
CTRL_PORT = 7715  # порт на котором слушают контроллеры (для команд)

# Известные контроллеры из дампа — заполняется автоматически
controllers = {}  # ip -> {mac, last_seen, status}


def parse_mac(data: bytes, offset: int = 6) -> str:
    """MAC контроллера из байт 6-10 пакета."""
    return "0B:3A:00:%02X:%02X" % (data[9], data[10])


def parse_event_packet(data: bytes, src_ip: str) -> dict | None:
    """
    Парсит пакет события прохода (LEN=32, байт[4]=0x08).
    Возвращает dict с данными события или None если не событие.
    """
    if len(data) != 32:
        return None
    if data[0] != 0x23:
        return None
    if data[4] != 0x08:
        return None

    mac = parse_mac(data)

    # Точка прохода: 04=считыватель1(вход), 05=считыватель2(выход)
    reader = data[12]
    direction = "in" if reader == 0x04 else "out" if reader == 0x05 else "unknown"

    # Дата/время из контроллера (часы могут быть сбиты — используем серверное время)
    ctrl_day  = data[13]
    ctrl_mon  = data[14]
    ctrl_year = data[15] + 2000
    ctrl_hour = data[16]
    ctrl_min  = data[17]

    # ID карты — 3 байта big-endian
    card_id = (data[22] << 16) | (data[23] << 8) | data[24]
    card_hex = "%02X%02X%02X" % (data[22], data[23], data[24])

    # Счётчик события (инкрементируется в контроллере)
    event_counter = data[26]

    # ID записи в памяти контроллера
    record_id = (data[28] << 8) | data[29]

    return {
        "controller_ip":   src_ip,
        "controller_mac":  mac,
        "direction":       direction,
        "reader":          reader,
        "card_id":         card_id,
        "card_hex":        card_hex,
        "event_counter":   event_counter,
        "record_id":       record_id,
        "ctrl_datetime":   f"{ctrl_day:02d}.{ctrl_mon:02d}.{ctrl_year} {ctrl_hour:02d}:{ctrl_min:02d}",
        "server_time":     datetime.datetime.now().isoformat(),
    }


def parse_heartbeat_packet(data: bytes, src_ip: str) -> dict | None:
    """
    Парсит heartbeat пакет (LEN=63, байт[4]=0x01).
    Возвращает статус контроллера.
    """
    if len(data) != 63:
        return None
    if data[0] != 0x23:
        return None
    if data[4] != 0x01:
        return None

    mac = parse_mac(data)

    # Количество точек прохода (байт 13)
    num_readers = data[13]

    # Режим работы (байт 3): 0x0E=контроль, возможно другие
    mode_byte = data[3]
    mode = {0x0E: "control", 0x00: "open", 0x01: "closed"}.get(mode_byte, "unknown")

    return {
        "ip":          src_ip,
        "mac":         mac,
        "mode":        mode,
        "num_readers": num_readers,
        "last_seen":   datetime.datetime.now().isoformat(),
    }


async def send_command(controller_ip: str, command: bytes):
    """Отправка команды контроллеру по UDP."""
    try:
        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        await loop.sock_sendto(sock, command, (controller_ip, CTRL_PORT))
        sock.close()
        logger.info(f"Command sent to {controller_ip}: {command.hex()}")
    except Exception as e:
        logger.error(f"Failed to send command to {controller_ip}: {e}")


async def cmd_open(controller_ip: str, point: int = 1):
    """Открыть турникет/замок."""
    # Команда открытия — на основе документации sendhex
    cmd = bytes([0x23, 0x00, 0x08, 0x00, 0x01, 0x00, 0x00, 0x00])
    await send_command(controller_ip, cmd)


async def cmd_close(controller_ip: str):
    """Закрыть турникет/замок."""
    cmd = bytes([0x23, 0x00, 0x08, 0x00, 0x02, 0x00, 0x00, 0x00])
    await send_command(controller_ip, cmd)


class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        logger.info(f"UDP listener started on port {UDP_PORT}")

    def datagram_received(self, data: bytes, addr):
        src_ip = addr[0]
        asyncio.create_task(self.process_packet(data, src_ip))

    async def process_packet(self, data: bytes, src_ip: str):
        try:
            if len(data) == 32 and data[4] == 0x08:
                # Событие прохода
                event = parse_event_packet(data, src_ip)
                if not event:
                    return

                # Ищем сотрудника по карте
                employee = await db_get_employee_by_card(event["card_hex"])
                if employee:
                    event["employee_id"]   = employee["id"]
                    event["employee_name"] = employee["full_name"]
                    event["department"]    = employee["department"]
                else:
                    event["employee_id"]   = None
                    event["employee_name"] = "Неизвестная карта"
                    event["department"]    = ""

                # Сохраняем в БД
                event_id = await db_add_event(event)
                event["id"] = event_id

                # Рассылаем по WebSocket всем подключённым клиентам
                await ws_manager.broadcast({
                    "type":  "event",
                    "data":  event,
                })

                logger.info(
                    f"EVENT: {src_ip} | card={event['card_hex']} | "
                    f"dir={event['direction']} | emp={event['employee_name']}"
                )

            elif len(data) == 63 and data[4] == 0x01:
                # Heartbeat от контроллера
                hb = parse_heartbeat_packet(data, src_ip)
                if not hb:
                    return

                controllers[src_ip] = hb
                await db_update_controller_status(hb)

                await ws_manager.broadcast({
                    "type": "controller_status",
                    "data": hb,
                })

            else:
                logger.debug(f"Unknown packet from {src_ip}: len={len(data)} data={data[:8].hex()}")

        except Exception as e:
            logger.error(f"Error processing packet from {src_ip}: {e}", exc_info=True)

    def error_received(self, exc):
        logger.error(f"UDP error: {exc}")

    def connection_lost(self, exc):
        logger.warning("UDP connection lost")


async def start_udp_listener():
    """Запуск UDP-сервера."""
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        UDPProtocol,
        local_addr=("0.0.0.0", UDP_PORT),
    )
    logger.info(f"UDP daemon listening on 0.0.0.0:{UDP_PORT}")
    return transport

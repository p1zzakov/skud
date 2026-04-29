"""
Миграция из ЭНТ — исправленная версия.
Связь: FB_KEY.ID = FB_KEY_H.ID → FB_KEY_H.USR = FB_USR.ID
"""
import asyncio
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DB_PATH", "/opt/skud/data/skud.db")

from database import init_db, DB_PATH
import aiosqlite

FB_HOST = "localhost"
FB_DB   = "/opt/skud/data/CBASE.FDB"
FB_USER = "SYSDBA"
FB_PASS = "masterkey"


def connect_fb():
    import fdb
    return fdb.connect(host=FB_HOST, database=FB_DB,
                       user=FB_USER, password=FB_PASS, charset='WIN1251')

def fetch(con, sql):
    cur = con.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


async def migrate():
    logger.info("Подключение к Firebird...")
    con = connect_fb()

    pods    = fetch(con, "SELECT ID, NAME FROM FB_POD")
    pod_map = {r["ID"]: (r["NAME"] or "").strip() for r in pods}
    logger.info(f"Подразделений: {len(pod_map)}")

    users = fetch(con, "SELECT ID, TABNUM, FNAME, LNAME, SNAME, DOLZ, PODR FROM FB_USR")
    logger.info(f"Сотрудников: {len(users)}")

    cards = fetch(con, """
        SELECT k.INHEX, h.USR
        FROM FB_KEY k
        JOIN FB_KEY_H h ON h.ID = k.ID
        WHERE k.INHEX IS NOT NULL AND k.INHEX != ''
    """)
    logger.info(f"Карт с привязкой: {len(cards)}")

    devices = fetch(con, "SELECT ID, NAME, IP FROM FB_DVS")
    logger.info(f"Контроллеров: {len(devices)}")
    con.close()

    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cards")
        await db.execute("DELETE FROM employees")
        await db.commit()

        emp_count = 0
        fb_id_to_our_id = {}

        for u in users:
            fname = (u.get("FNAME") or "").strip()
            lname = (u.get("LNAME") or "").strip()
            sname = (u.get("SNAME") or "").strip()
            full_name = " ".join(p for p in [lname, fname, sname] if p)
            if not full_name:
                continue

            tab  = (str(u.get("TABNUM") or "")).strip()
            dept = pod_map.get(u.get("PODR"), "")
            pos  = str(u.get("DOLZ") or "").strip()

            cur = await db.execute("""
                INSERT OR REPLACE INTO employees (tab_number, full_name, department, position)
                VALUES (?, ?, ?, ?)
            """, (tab, full_name, dept, pos))
            fb_id_to_our_id[u["ID"]] = cur.lastrowid
            emp_count += 1

        await db.commit()
        logger.info(f"Импортировано сотрудников: {emp_count}")

        card_count   = 0
        no_emp_count = 0

        for card in cards:
            hex_val    = (card["INHEX"] or "").strip().upper()
            fb_user_id = card["USR"]
            our_emp_id = fb_id_to_our_id.get(fb_user_id)

            if not hex_val:
                continue
            if not our_emp_id:
                no_emp_count += 1

            try:
                await db.execute("""
                    INSERT OR IGNORE INTO cards (card_hex, employee_id)
                    VALUES (?, ?)
                """, (hex_val, our_emp_id))
                card_count += 1
            except Exception as e:
                logger.warning(f"Карта {hex_val}: {e}")

        await db.commit()
        logger.info(f"Импортировано карт: {card_count}")
        if no_emp_count:
            logger.warning(f"Карт без сотрудника: {no_emp_count}")

        for d in devices:
            ip   = (d.get("IP")   or "").strip()
            name = (d.get("NAME") or "").strip()
            if not ip:
                continue
            await db.execute("""
                INSERT OR IGNORE INTO controllers (ip, name)
                VALUES (?, ?)
                ON CONFLICT(ip) DO UPDATE SET name=excluded.name
            """, (ip, name or ip))
        await db.commit()

    logger.info("Миграция завершена!")
    logger.info(f"  Сотрудников:  {emp_count}")
    logger.info(f"  Карт:         {card_count}")
    logger.info(f"  Контроллеров: {len(devices)}")


if __name__ == "__main__":
    asyncio.run(migrate())
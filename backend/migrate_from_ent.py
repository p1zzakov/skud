#!/usr/bin/env python3
"""
Скрипт миграции данных из ЭНТ (Firebird) в новую СКУД (SQLite).

Использование:
    pip install fdb
    python migrate_from_ent.py --host 192.168.1.54 --db "C:/Program Files/ENT/Server/DB/skud.fdb"

Или если Firebird недоступен — экспорт через CSV:
    python migrate_from_ent.py --csv employees.csv cards.csv
"""
import argparse
import asyncio
import sys
import os
import csv
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Путь к новой БД
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DB_PATH", "/opt/skud/data/skud.db")

from database import init_db, DB_PATH
import aiosqlite


async def migrate_from_firebird(host: str, db_path: str, user: str = "SYSDBA", password: str = "masterkey"):
    """Подключение к Firebird ЭНТ и перенос данных."""
    try:
        import fdb
    except ImportError:
        logger.error("Установите: pip install fdb")
        sys.exit(1)

    logger.info(f"Connecting to Firebird {host}:{db_path}")
    con = fdb.connect(host=host, database=db_path, user=user, password=password, charset="UTF8")
    cur = con.cursor()

    # Смотрим таблицы ЭНТ
    cur.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG=0 ORDER BY 1")
    tables = [r[0].strip() for r in cur.fetchall()]
    logger.info(f"Tables in ENT DB: {tables}")

    employees_data = []
    cards_data     = []

    # Пробуем стандартные имена таблиц ЭНТ
    # (могут отличаться в разных версиях — смотри список выше)
    emp_table  = next((t for t in tables if "EMPLOY" in t or "PERSON" in t or "WORKER" in t or "STAFF" in t), None)
    card_table = next((t for t in tables if "CARD" in t or "KEY"   in t or "PASS"   in t), None)

    if emp_table:
        logger.info(f"Found employee table: {emp_table}")
        cur.execute(f"SELECT * FROM {emp_table} ROWS 1")
        cols = [d[0] for d in cur.description]
        logger.info(f"Columns: {cols}")
        cur.execute(f"SELECT * FROM {emp_table}")
        rows = cur.fetchall()
        logger.info(f"Employees found: {len(rows)}")

        # Маппинг колонок — адаптируй под реальные названия
        for row in rows:
            r = dict(zip(cols, row))
            employees_data.append({
                "tab_number": str(r.get("TAB_NUMBER") or r.get("TABNUM") or r.get("ID") or ""),
                "full_name":  str(r.get("FIO") or r.get("FULLNAME") or r.get("NAME") or "Без имени"),
                "department": str(r.get("DEPT") or r.get("DEPARTMENT") or r.get("OTDEL") or ""),
                "position":   str(r.get("POST") or r.get("POSITION") or r.get("DOLZHNOST") or ""),
                "phone":      str(r.get("PHONE") or r.get("TEL") or ""),
            })
    else:
        logger.warning("Employee table not found! Try --show-tables to see all tables.")

    if card_table:
        logger.info(f"Found card table: {card_table}")
        cur.execute(f"SELECT * FROM {card_table} ROWS 1")
        cols = [d[0] for d in cur.description]
        logger.info(f"Card columns: {cols}")
        cur.execute(f"SELECT * FROM {card_table}")
        rows = cur.fetchall()
        logger.info(f"Cards found: {len(rows)}")

        for row in rows:
            r = dict(zip(cols, row))
            card_num = r.get("CARD_NUM") or r.get("CARDNUM") or r.get("CODE") or r.get("KEYCODE")
            emp_id   = r.get("PERSON_ID") or r.get("EMPLOYEE_ID") or r.get("WORKER_ID")
            if card_num:
                # Конвертируем число в hex (формат нашего сниффера)
                try:
                    card_int = int(card_num)
                    card_hex = "%06X" % card_int
                except (ValueError, TypeError):
                    card_hex = str(card_num).upper()
                cards_data.append({
                    "card_hex":    card_hex,
                    "employee_tab": str(emp_id or ""),
                })

    con.close()
    return employees_data, cards_data


async def migrate_from_csv(employees_csv: str, cards_csv: str = None):
    """Импорт из CSV файлов."""
    employees_data = []
    cards_data     = []

    if employees_csv and os.path.exists(employees_csv):
        with open(employees_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                employees_data.append({
                    "tab_number": row.get("tab_number") or row.get("Табельный") or "",
                    "full_name":  row.get("full_name")  or row.get("ФИО") or "Без имени",
                    "department": row.get("department") or row.get("Отдел") or "",
                    "position":   row.get("position")   or row.get("Должность") or "",
                    "phone":      row.get("phone")       or row.get("Телефон") or "",
                })
        logger.info(f"Read {len(employees_data)} employees from CSV")

    if cards_csv and os.path.exists(cards_csv):
        with open(cards_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cards_data.append({
                    "card_hex":    (row.get("card_hex") or row.get("Карта") or "").upper(),
                    "employee_tab": row.get("tab_number") or row.get("Табельный") or "",
                })
        logger.info(f"Read {len(cards_data)} cards from CSV")

    return employees_data, cards_data


async def save_to_db(employees_data: list, cards_data: list):
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        # Сотрудники
        emp_count = 0
        tab_to_id = {}
        for emp in employees_data:
            if not emp["full_name"] or emp["full_name"] == "Без имени":
                continue
            cur = await db.execute("""
                INSERT OR IGNORE INTO employees (tab_number, full_name, department, position, phone)
                VALUES (?,?,?,?,?)
            """, (emp["tab_number"], emp["full_name"], emp["department"],
                  emp["position"], emp.get("phone", "")))
            if cur.lastrowid:
                tab_to_id[emp["tab_number"]] = cur.lastrowid
                emp_count += 1

        await db.commit()
        logger.info(f"Imported {emp_count} employees")

        # Получаем все tab_number -> id
        async with db.execute("SELECT id, tab_number FROM employees") as cur:
            rows = await cur.fetchall()
            for row in rows:
                tab_to_id[str(row[1])] = row[0]

        # Карты
        card_count = 0
        for card in cards_data:
            if not card["card_hex"]:
                continue
            emp_id = tab_to_id.get(card["employee_tab"])
            if not emp_id:
                logger.warning(f"Employee not found for card {card['card_hex']} tab={card['employee_tab']}")
                continue
            await db.execute("""
                INSERT OR IGNORE INTO cards (card_hex, employee_id)
                VALUES (?,?)
            """, (card["card_hex"], emp_id))
            card_count += 1

        await db.commit()
        logger.info(f"Imported {card_count} cards")


async def show_tables(host: str, db_path: str, user: str, password: str):
    try:
        import fdb
        con = fdb.connect(host=host, database=db_path, user=user, password=password, charset="UTF8")
        cur = con.cursor()
        cur.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG=0 ORDER BY 1")
        tables = [r[0].strip() for r in cur.fetchall()]
        print("\nТаблицы в БД ЭНТ:")
        for t in tables:
            cur.execute(f"SELECT * FROM {t} ROWS 1")
            cols = [d[0] for d in cur.description]
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = cur.fetchone()[0]
            print(f"  {t:<30} {cnt:>6} строк  | Колонки: {', '.join(cols[:8])}")
        con.close()
    except Exception as e:
        print(f"Ошибка: {e}")


def main():
    parser = argparse.ArgumentParser(description="Миграция данных из ЭНТ в СКУД")
    parser.add_argument("--host",         default="192.168.1.54", help="IP сервера ЭНТ (Firebird)")
    parser.add_argument("--db",           default="C:/Program Files/ENT/Server/DB/skud.fdb")
    parser.add_argument("--user",         default="SYSDBA")
    parser.add_argument("--password",     default="masterkey")
    parser.add_argument("--csv-emp",      help="CSV файл с сотрудниками")
    parser.add_argument("--csv-cards",    help="CSV файл с картами")
    parser.add_argument("--show-tables",  action="store_true", help="Показать таблицы Firebird")
    args = parser.parse_args()

    if args.show_tables:
        asyncio.run(show_tables(args.host, args.db, args.user, args.password))
        return

    if args.csv_emp:
        employees, cards = asyncio.run(migrate_from_csv(args.csv_emp, args.csv_cards))
    else:
        employees, cards = asyncio.run(migrate_from_firebird(
            args.host, args.db, args.user, args.password
        ))

    if employees:
        asyncio.run(save_to_db(employees, cards))
    else:
        logger.warning("Нет данных для импорта")


if __name__ == "__main__":
    main()

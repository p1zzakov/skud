"""
База данных — SQLite через aiosqlite.
Иерархия: Company -> City -> Department -> Controllers
          Employee -> Department -> access to controllers
"""
import aiosqlite
import logging
import datetime
import hashlib
import os

logger = logging.getLogger(__name__)
DB_PATH = os.environ.get("DB_PATH", "/opt/skud/data/skud.db")


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            -- Компании
            CREATE TABLE IF NOT EXISTS companies (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                short_name TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Города
            CREATE TABLE IF NOT EXISTS cities (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                name       TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Подразделения
            CREATE TABLE IF NOT EXISTS departments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                city_id    INTEGER REFERENCES cities(id) ON DELETE SET NULL,
                name       TEXT NOT NULL,
                color      TEXT DEFAULT '#6366f1',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Контроллеры
            CREATE TABLE IF NOT EXISTS controllers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ip          TEXT UNIQUE NOT NULL,
                mac         TEXT DEFAULT '',
                name        TEXT DEFAULT '',
                location    TEXT DEFAULT '',
                city_id     INTEGER REFERENCES cities(id) ON DELETE SET NULL,
                mode        TEXT DEFAULT 'control',
                num_readers INTEGER DEFAULT 1,
                last_seen   TEXT,
                online      INTEGER DEFAULT 0
            );

            -- Доступ подразделения к контроллеру
            CREATE TABLE IF NOT EXISTS department_access (
                department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
                controller_id INTEGER REFERENCES controllers(id) ON DELETE CASCADE,
                PRIMARY KEY (department_id, controller_id)
            );

            -- Сотрудники
            CREATE TABLE IF NOT EXISTS employees (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_number    TEXT,
                full_name     TEXT NOT NULL,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                department    TEXT DEFAULT '',
                position      TEXT DEFAULT '',
                phone         TEXT DEFAULT '',
                email         TEXT DEFAULT '',
                photo         TEXT DEFAULT '',
                active        INTEGER DEFAULT 1,
                created_at    TEXT DEFAULT (datetime('now','localtime')),
                updated_at    TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Карты
            CREATE TABLE IF NOT EXISTS cards (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                card_hex    TEXT UNIQUE NOT NULL,
                employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                card_type   TEXT DEFAULT 'standard',
                active      INTEGER DEFAULT 1,
                issued_at   TEXT DEFAULT (datetime('now','localtime')),
                note        TEXT DEFAULT ''
            );

            -- События
            CREATE TABLE IF NOT EXISTS events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                controller_ip   TEXT NOT NULL,
                controller_mac  TEXT DEFAULT '',
                controller_name TEXT DEFAULT '',
                direction       TEXT NOT NULL,
                reader          INTEGER DEFAULT 0,
                card_id         INTEGER,
                card_hex        TEXT NOT NULL,
                employee_id     INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                employee_name   TEXT DEFAULT '',
                department      TEXT DEFAULT '',
                photo           TEXT DEFAULT '',
                event_counter   INTEGER DEFAULT 0,
                record_id       INTEGER DEFAULT 0,
                ctrl_datetime   TEXT DEFAULT '',
                server_time     TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_events_time   ON events(server_time DESC);
            CREATE INDEX IF NOT EXISTS idx_events_emp    ON events(employee_id);
            CREATE INDEX IF NOT EXISTS idx_events_card   ON events(card_hex);
            CREATE INDEX IF NOT EXISTS idx_events_ctrl   ON events(controller_ip);
            CREATE INDEX IF NOT EXISTS idx_cards_hex     ON cards(card_hex);

            -- Пользователи системы
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                role       TEXT DEFAULT 'viewer',
                full_name  TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
        """)

        pw = hashlib.sha256(b"admin").hexdigest()
        await db.execute("""
            INSERT OR IGNORE INTO users (username, password, role, full_name)
            VALUES ('admin', ?, 'admin', 'Администратор')
        """, (pw,))
        await db.commit()
    logger.info(f"Database initialized: {DB_PATH}")


# ── Events ────────────────────────────────────────────────────────
async def db_get_employee_by_card(card_hex: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.id, e.full_name, e.department, e.department_id, e.position,
                   e.tab_number, e.photo
            FROM cards c
            JOIN employees e ON e.id = c.employee_id
            WHERE c.card_hex = ? AND c.active = 1 AND e.active = 1
        """, (card_hex.upper(),)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def db_add_event(event: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO events
                (controller_ip, controller_mac, controller_name, direction, reader,
                 card_id, card_hex, employee_id, employee_name, department, photo,
                 event_counter, record_id, ctrl_datetime, server_time)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            event["controller_ip"], event["controller_mac"],
            event.get("controller_name", ""),
            event["direction"], event["reader"],
            event["card_id"], event["card_hex"].upper(),
            event.get("employee_id"), event.get("employee_name", ""),
            event.get("department", ""), event.get("photo", ""),
            event["event_counter"], event["record_id"],
            event["ctrl_datetime"], event["server_time"],
        ))
        await db.commit()
        return cur.lastrowid


async def db_update_controller_status(hb: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO controllers (ip, mac, mode, num_readers, last_seen, online)
            VALUES (?,?,?,?,?,1)
            ON CONFLICT(ip) DO UPDATE SET
                mac=excluded.mac, mode=excluded.mode,
                num_readers=excluded.num_readers,
                last_seen=excluded.last_seen, online=1
        """, (hb["ip"], hb["mac"], hb["mode"], hb["num_readers"], hb["last_seen"]))
        await db.commit()


async def db_get_events(limit=100, offset=0, employee_id=None,
                        controller_ip=None, date_from=None, date_to=None,
                        direction=None) -> list:
    filters, params = [], []
    if employee_id:
        filters.append("employee_id=?"); params.append(employee_id)
    if controller_ip:
        filters.append("controller_ip=?"); params.append(controller_ip)
    if date_from:
        filters.append("server_time>=?"); params.append(date_from)
    if date_to:
        filters.append("server_time<=?"); params.append(date_to)
    if direction:
        filters.append("direction=?"); params.append(direction)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT * FROM events {where}
            ORDER BY server_time DESC LIMIT ? OFFSET ?
        """, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Employees ─────────────────────────────────────────────────────
async def db_get_employees(search=None, department_id=None, active=1) -> list:
    filters = ["e.active=?"]
    params  = [active]
    if search:
        filters.append("(e.full_name LIKE ? OR e.tab_number LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if department_id:
        filters.append("e.department_id=?"); params.append(department_id)
    where = "WHERE " + " AND ".join(filters)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT e.*,
                   d.name as dept_name,
                   ci.name as city_name,
                   co.name as company_name,
                   GROUP_CONCAT(c.card_hex, ',') as cards
            FROM employees e
            LEFT JOIN departments d  ON d.id  = e.department_id
            LEFT JOIN cities      ci ON ci.id = d.city_id
            LEFT JOIN companies   co ON co.id = ci.company_id
            LEFT JOIN cards       c  ON c.employee_id = e.id AND c.active=1
            {where}
            GROUP BY e.id
            ORDER BY e.full_name
        """, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Controllers ───────────────────────────────────────────────────
async def db_get_controllers() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE controllers SET online=0
            WHERE last_seen < datetime('now','-30 seconds','localtime')
               OR last_seen IS NULL
        """)
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.*, ci.name as city_name, co.name as company_name
            FROM controllers c
            LEFT JOIN cities    ci ON ci.id = c.city_id
            LEFT JOIN companies co ON co.id = ci.company_id
            ORDER BY c.ip
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Structure ─────────────────────────────────────────────────────
async def db_get_companies() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT co.*,
                   COUNT(DISTINCT ci.id) as city_count,
                   COUNT(DISTINCT d.id)  as dept_count
            FROM companies co
            LEFT JOIN cities      ci ON ci.company_id = co.id
            LEFT JOIN departments d  ON d.city_id     = ci.id
            GROUP BY co.id ORDER BY co.name
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_get_cities(company_id=None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = """
            SELECT ci.*, co.name as company_name,
                   COUNT(DISTINCT d.id) as dept_count
            FROM cities ci
            LEFT JOIN companies   co ON co.id = ci.company_id
            LEFT JOIN departments d  ON d.city_id = ci.id
        """
        params = []
        if company_id:
            q += " WHERE ci.company_id=?"; params.append(company_id)
        q += " GROUP BY ci.id ORDER BY co.name, ci.name"
        async with db.execute(q, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_get_departments(city_id=None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = """
            SELECT d.*,
                   ci.name as city_name,
                   co.name as company_name,
                   COUNT(DISTINCT e.id)  as emp_count,
                   COUNT(DISTINCT da.controller_id) as ctrl_count,
                   GROUP_CONCAT(DISTINCT c.ip) as controller_ips
            FROM departments d
            LEFT JOIN cities      ci ON ci.id = d.city_id
            LEFT JOIN companies   co ON co.id = ci.company_id
            LEFT JOIN employees   e  ON e.department_id = d.id AND e.active=1
            LEFT JOIN department_access da ON da.department_id = d.id
            LEFT JOIN controllers c  ON c.id = da.controller_id
        """
        params = []
        if city_id:
            q += " WHERE d.city_id=?"; params.append(city_id)
        q += " GROUP BY d.id ORDER BY co.name, ci.name, d.name"
        async with db.execute(q, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Reports ───────────────────────────────────────────────────────
async def db_get_report(employee_id: int, date_from: str, date_to: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT server_time, direction, controller_ip, controller_name, card_hex
            FROM events
            WHERE employee_id=? AND server_time>=? AND server_time<=?
            ORDER BY server_time
        """, (employee_id, date_from, date_to)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_get_presence(date: str) -> list:
    date_from = f"{date} 00:00:00"
    date_to   = f"{date} 23:59:59"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.id, e.full_name, e.department, e.photo,
                   MAX(CASE WHEN ev.direction='in'  THEN ev.server_time END) as last_in,
                   MAX(CASE WHEN ev.direction='out' THEN ev.server_time END) as last_out
            FROM employees e
            JOIN events ev ON ev.employee_id=e.id
            WHERE ev.server_time>=? AND ev.server_time<=?
            GROUP BY e.id
            HAVING last_in > COALESCE(last_out,'0')
            ORDER BY last_in DESC
        """, (date_from, date_to)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM employees WHERE active=1") as c:
            emp = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM events WHERE date(server_time)=date('now','localtime')") as c:
            today = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM controllers WHERE online=1") as c:
            online = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM controllers") as c:
            total = (await c.fetchone())[0]
        return {"employees": emp, "today_events": today,
                "controllers_online": online, "controllers_total": total}
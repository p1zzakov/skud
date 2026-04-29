"""СКУД КЕЛЕТ — FastAPI backend"""
import asyncio, logging, os, hashlib, datetime
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import aiosqlite

from database import (
    init_db, DB_PATH, db_get_events, db_get_employees, db_get_controllers,
    db_get_companies, db_get_cities, db_get_departments,
    db_get_report, db_get_presence, db_get_stats,
    db_get_employee_by_card, db_add_event, db_update_controller_status
)
from ws_manager import ws_manager
from udp_daemon import start_udp_listener, cmd_open, cmd_close

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

udp_transport = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global udp_transport
    await init_db()
    udp_transport = await start_udp_listener()
    yield
    if udp_transport:
        udp_transport.close()

app = FastAPI(title="СКУД КЕЛЕТ", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── WebSocket ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)

# ── Auth ──────────────────────────────────────────────────────────
class LoginReq(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
async def login(req: LoginReq):
    pw = hashlib.sha256(req.password.encode()).hexdigest()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (req.username, pw)) as cur:
            user = await cur.fetchone()
    if not user:
        raise HTTPException(401, "Неверный логин или пароль")
    return {"ok": True, "role": user["role"], "full_name": user["full_name"]}

# ── Stats ─────────────────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    return await db_get_stats()

# ── Events ────────────────────────────────────────────────────────
@app.get("/api/events")
async def get_events(
    limit: int = Query(100, le=1000), offset: int = 0,
    employee_id: Optional[int] = None, controller_ip: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    direction: Optional[str] = None,
):
    events = await db_get_events(limit=limit, offset=offset,
        employee_id=employee_id, controller_ip=controller_ip,
        date_from=date_from, date_to=date_to, direction=direction)
    return {"events": events, "count": len(events)}

# ── Employees ─────────────────────────────────────────────────────
@app.get("/api/employees")
async def get_employees(search: Optional[str] = None,
                        department_id: Optional[int] = None,
                        active: int = 1):
    return await db_get_employees(search=search,
                                   department_id=department_id, active=active)

@app.get("/api/employees/{emp_id}")
async def get_employee(emp_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.*, d.name as dept_name
            FROM employees e
            LEFT JOIN departments d ON d.id=e.department_id
            WHERE e.id=?
        """, (emp_id,)) as cur:
            row = await cur.fetchone()
    if not row: raise HTTPException(404, "Не найден")
    return dict(row)

class EmpBody(BaseModel):
    tab_number:    Optional[str] = None
    full_name:     str
    department_id: Optional[int] = None
    position:      str = ""
    phone:         str = ""
    email:         str = ""

@app.post("/api/employees")
async def create_employee(b: EmpBody):
    dept_name = ""
    if b.department_id:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT name FROM departments WHERE id=?",
                                  (b.department_id,)) as cur:
                r = await cur.fetchone()
                dept_name = r[0] if r else ""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO employees
                (tab_number,full_name,department_id,department,position,phone,email)
            VALUES (?,?,?,?,?,?,?)
        """, (b.tab_number, b.full_name, b.department_id, dept_name,
              b.position, b.phone, b.email))
        await db.commit()
        return {"id": cur.lastrowid, "ok": True}

@app.put("/api/employees/{emp_id}")
async def update_employee(emp_id: int, b: EmpBody):
    dept_name = ""
    if b.department_id:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT name FROM departments WHERE id=?",
                                  (b.department_id,)) as cur:
                r = await cur.fetchone()
                dept_name = r[0] if r else ""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE employees SET
                tab_number=?,full_name=?,department_id=?,department=?,
                position=?,phone=?,email=?,
                updated_at=datetime('now','localtime')
            WHERE id=?
        """, (b.tab_number, b.full_name, b.department_id, dept_name,
              b.position, b.phone, b.email, emp_id))
        await db.commit()
    return {"ok": True}

@app.delete("/api/employees/{emp_id}")
async def delete_employee(emp_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET active=0 WHERE id=?", (emp_id,))
        await db.commit()
    return {"ok": True}

# ── Cards ─────────────────────────────────────────────────────────
@app.get("/api/cards")
async def get_cards(employee_id: Optional[int] = None):
    q = "SELECT c.*,e.full_name FROM cards c LEFT JOIN employees e ON e.id=c.employee_id"
    p = []
    if employee_id:
        q += " WHERE c.employee_id=?"; p.append(employee_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(q, p) as cur:
            return [dict(r) for r in await cur.fetchall()]

class CardBody(BaseModel):
    card_hex:    str
    employee_id: int
    note:        str = ""

@app.post("/api/cards")
async def create_card(b: CardBody):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute("""
                INSERT INTO cards (card_hex,employee_id,note) VALUES (?,?,?)
            """, (b.card_hex.upper(), b.employee_id, b.note))
            await db.commit()
            return {"id": cur.lastrowid, "ok": True}
        except Exception as e:
            raise HTTPException(400, f"Карта уже существует: {e}")

@app.delete("/api/cards/{card_id}")
async def delete_card(card_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE cards SET active=0 WHERE id=?", (card_id,))
        await db.commit()
    return {"ok": True}

# ── Controllers ───────────────────────────────────────────────────
@app.get("/api/controllers")
async def get_controllers():
    return await db_get_controllers()

class CtrlBody(BaseModel):
    name:     str = ""
    location: str = ""
    city_id:  Optional[int] = None

@app.put("/api/controllers/{ctrl_id}")
async def update_controller(ctrl_id: int, b: CtrlBody):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE controllers SET name=?,location=?,city_id=? WHERE id=?
        """, (b.name, b.location, b.city_id, ctrl_id))
        await db.commit()
    return {"ok": True}

class CmdBody(BaseModel):
    action: str

@app.post("/api/controllers/{ip}/command")
async def ctrl_command(ip: str, b: CmdBody):
    if b.action == "open":   await cmd_open(ip)
    elif b.action == "close": await cmd_close(ip)
    else: raise HTTPException(400, "Unknown action")
    return {"ok": True}

# ── Structure: Companies ──────────────────────────────────────────
@app.get("/api/companies")
async def get_companies():
    return await db_get_companies()

class CompanyBody(BaseModel):
    name:       str
    short_name: str = ""

@app.post("/api/companies")
async def create_company(b: CompanyBody):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO companies (name,short_name) VALUES (?,?)",
            (b.name, b.short_name))
        await db.commit()
    return {"id": cur.lastrowid, "ok": True}

@app.put("/api/companies/{cid}")
async def update_company(cid: int, b: CompanyBody):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE companies SET name=?,short_name=? WHERE id=?",
                         (b.name, b.short_name, cid))
        await db.commit()
    return {"ok": True}

@app.delete("/api/companies/{cid}")
async def delete_company(cid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM companies WHERE id=?", (cid,))
        await db.commit()
    return {"ok": True}

# ── Structure: Cities ─────────────────────────────────────────────
@app.get("/api/cities")
async def get_cities(company_id: Optional[int] = None):
    return await db_get_cities(company_id)

class CityBody(BaseModel):
    company_id: int
    name:       str

@app.post("/api/cities")
async def create_city(b: CityBody):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO cities (company_id,name) VALUES (?,?)",
            (b.company_id, b.name))
        await db.commit()
    return {"id": cur.lastrowid, "ok": True}

@app.put("/api/cities/{cid}")
async def update_city(cid: int, b: CityBody):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE cities SET company_id=?,name=? WHERE id=?",
                         (b.company_id, b.name, cid))
        await db.commit()
    return {"ok": True}

@app.delete("/api/cities/{cid}")
async def delete_city(cid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cities WHERE id=?", (cid,))
        await db.commit()
    return {"ok": True}

# ── Structure: Departments ────────────────────────────────────────
@app.get("/api/departments")
async def get_departments(city_id: Optional[int] = None):
    return await db_get_departments(city_id)

class DeptBody(BaseModel):
    city_id:     Optional[int] = None
    name:        str
    color:       str = "#6366f1"
    controller_ids: list[int] = []

@app.post("/api/departments")
async def create_department(b: DeptBody):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO departments (city_id,name,color) VALUES (?,?,?)",
            (b.city_id, b.name, b.color))
        dept_id = cur.lastrowid
        for cid in b.controller_ids:
            await db.execute("""
                INSERT OR IGNORE INTO department_access (department_id,controller_id)
                VALUES (?,?)
            """, (dept_id, cid))
        await db.commit()
    return {"id": dept_id, "ok": True}

@app.put("/api/departments/{did}")
async def update_department(did: int, b: DeptBody):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE departments SET city_id=?,name=?,color=? WHERE id=?",
            (b.city_id, b.name, b.color, did))
        await db.execute(
            "DELETE FROM department_access WHERE department_id=?", (did,))
        for cid in b.controller_ids:
            await db.execute("""
                INSERT OR IGNORE INTO department_access (department_id,controller_id)
                VALUES (?,?)
            """, (did, cid))
        await db.commit()
    return {"ok": True}

@app.delete("/api/departments/{did}")
async def delete_department(did: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM departments WHERE id=?", (did,))
        await db.commit()
    return {"ok": True}

# ── Reports ───────────────────────────────────────────────────────
@app.get("/api/report/employee/{emp_id}")
async def report_employee(emp_id: int,
                          date_from: str = Query(...),
                          date_to:   str = Query(...)):
    raw = await db_get_report(emp_id, date_from, date_to)
    days = {}
    for ev in raw:
        day = ev["server_time"][:10]
        if day not in days:
            days[day] = {"date": day, "first_in": None,
                         "last_out": None, "events": []}
        days[day]["events"].append(ev)
        if ev["direction"] == "in" and not days[day]["first_in"]:
            days[day]["first_in"] = ev["server_time"]
        if ev["direction"] == "out":
            days[day]["last_out"] = ev["server_time"]
    return {"employee_id": emp_id,
            "report": sorted(days.values(), key=lambda x: x["date"])}

@app.get("/api/report/presence")
async def report_presence(date: Optional[str] = None):
    if not date:
        date = datetime.date.today().isoformat()
    return {"date": date, "present": await db_get_presence(date)}

# ── Schedules ─────────────────────────────────────────────────────
from typing import List as TList

class ScheduleBody(BaseModel):
    name:        str
    description: str = ""
    mon_start: str=""; mon_end: str=""
    tue_start: str=""; tue_end: str=""
    wed_start: str=""; wed_end: str=""
    thu_start: str=""; thu_end: str=""
    fri_start: str=""; fri_end: str=""
    sat_start: str=""; sat_end: str=""
    sun_start: str=""; sun_end: str=""
    department_ids: TList[int] = []
    employee_ids:   TList[int] = []

@app.get("/api/schedules")
async def get_schedules():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*,
                   GROUP_CONCAT(DISTINCT ds.department_id) as dept_ids,
                   GROUP_CONCAT(DISTINCT es.employee_id)   as emp_ids
            FROM schedules s
            LEFT JOIN department_schedules ds ON ds.schedule_id=s.id
            LEFT JOIN employee_schedules   es ON es.schedule_id=s.id
            GROUP BY s.id ORDER BY s.name
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]

@app.post("/api/schedules")
async def create_schedule(b: ScheduleBody):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO schedules
                (name,description,mon_start,mon_end,tue_start,tue_end,
                 wed_start,wed_end,thu_start,thu_end,fri_start,fri_end,
                 sat_start,sat_end,sun_start,sun_end)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (b.name,b.description,b.mon_start,b.mon_end,b.tue_start,b.tue_end,
              b.wed_start,b.wed_end,b.thu_start,b.thu_end,b.fri_start,b.fri_end,
              b.sat_start,b.sat_end,b.sun_start,b.sun_end))
        sid = cur.lastrowid
        for did in b.department_ids:
            await db.execute("INSERT OR IGNORE INTO department_schedules VALUES (?,?)",(did,sid))
        for eid in b.employee_ids:
            await db.execute("INSERT OR IGNORE INTO employee_schedules VALUES (?,?)",(eid,sid))
        await db.commit()
        return {"id": sid, "ok": True}

@app.put("/api/schedules/{sid}")
async def update_schedule(sid: int, b: ScheduleBody):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE schedules SET name=?,description=?,
                mon_start=?,mon_end=?,tue_start=?,tue_end=?,
                wed_start=?,wed_end=?,thu_start=?,thu_end=?,
                fri_start=?,fri_end=?,sat_start=?,sat_end=?,
                sun_start=?,sun_end=? WHERE id=?
        """, (b.name,b.description,b.mon_start,b.mon_end,b.tue_start,b.tue_end,
              b.wed_start,b.wed_end,b.thu_start,b.thu_end,b.fri_start,b.fri_end,
              b.sat_start,b.sat_end,b.sun_start,b.sun_end,sid))
        await db.execute("DELETE FROM department_schedules WHERE schedule_id=?",(sid,))
        await db.execute("DELETE FROM employee_schedules WHERE schedule_id=?",(sid,))
        for did in b.department_ids:
            await db.execute("INSERT OR IGNORE INTO department_schedules VALUES (?,?)",(did,sid))
        for eid in b.employee_ids:
            await db.execute("INSERT OR IGNORE INTO employee_schedules VALUES (?,?)",(eid,sid))
        await db.commit()
        return {"ok": True}

@app.delete("/api/schedules/{sid}")
async def delete_schedule(sid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM schedules WHERE id=?",(sid,))
        await db.commit()
        return {"ok": True}

# ── Users ─────────────────────────────────────────────────────────
class UserBody(BaseModel):
    username:  str
    password:  str = ""
    role:      str = "viewer"
    full_name: str = ""

@app.get("/api/users")
async def get_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id,username,role,full_name,created_at FROM users ORDER BY full_name"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

@app.post("/api/users")
async def create_user(b: UserBody):
    pw = hashlib.sha256(b.password.encode()).hexdigest() if b.password else ""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(
                "INSERT INTO users (username,password,role,full_name) VALUES (?,?,?,?)",
                (b.username, pw, b.role, b.full_name))
            await db.commit()
            return {"id": cur.lastrowid, "ok": True}
        except Exception as e:
            raise HTTPException(400, f"Пользователь уже существует: {e}")

@app.put("/api/users/{uid}")
async def update_user(uid: int, b: UserBody):
    async with aiosqlite.connect(DB_PATH) as db:
        if b.password:
            pw = hashlib.sha256(b.password.encode()).hexdigest()
            await db.execute(
                "UPDATE users SET username=?,password=?,role=?,full_name=? WHERE id=?",
                (b.username, pw, b.role, b.full_name, uid))
        else:
            await db.execute(
                "UPDATE users SET username=?,role=?,full_name=? WHERE id=?",
                (b.username, b.role, b.full_name, uid))
        await db.commit()
        return {"ok": True}

@app.delete("/api/users/{uid}")
async def delete_user(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE id=?",(uid,))
        await db.commit()
        return {"ok": True}

# ── Controller Discovery ──────────────────────────────────────────
@app.post("/api/controllers/discover")
async def discover_controllers(body: dict):
    import socket as _socket
    ip = body.get("ip","").strip()
    results = []
    if ip:
        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            sock.settimeout(2)
            probe = bytes([0x23,0x00,0x08,0x00,0xFF,0x00,0x00,0x00])
            sock.sendto(probe, (ip, 7715))
            try:
                data, addr = sock.recvfrom(1024)
                results.append({"ip": addr[0], "status": "online"})
            except:
                results.append({"ip": ip, "status": "no_response"})
            sock.close()
        except Exception as e:
            results.append({"ip": ip, "status": "no_response"})
    else:
        from udp_daemon import controllers
        for cip, info in controllers.items():
            results.append({"ip": cip, "mac": info.get("mac",""), "status": "online"})
    return {"controllers": results}

@app.post("/api/controllers/add")
async def add_controller(body: dict):
    ip   = body.get("ip","").strip()
    name = body.get("name", ip)
    if not ip:
        raise HTTPException(400, "IP обязателен")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO controllers (ip, name) VALUES (?,?)
            ON CONFLICT(ip) DO UPDATE SET name=excluded.name
        """, (ip, name))
        await db.commit()
    return {"ok": True}

# ── Static ────────────────────────────────────────────────────────
STATIC_DIR = "/opt/skud/frontend"
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

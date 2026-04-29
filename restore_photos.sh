#!/bin/bash
/opt/skud/venv/bin/python3 << 'PYEOF'
import fdb, os, sqlite3
PHOTO_DIR = "/opt/skud/frontend/photos"
os.makedirs(PHOTO_DIR, exist_ok=True)
fb = fdb.connect(host="localhost", database="/opt/skud/data/CBASE.FDB", user="SYSDBA", password="masterkey", charset="WIN1251")
fb_cur = fb.cursor()
fb_cur.execute("SELECT ID, TABNUM FROM FB_USR")
fb_id_to_tab = {row[0]: str(row[1] or "").strip() for row in fb_cur.fetchall()}
fb.close()
our_db = sqlite3.connect("/opt/skud/data/skud.db")
tab_to_our = {str(r[1] or "").strip(): r[0] for r in our_db.execute("SELECT id, tab_number FROM employees")}
gb = fdb.connect(host="localhost", database="/opt/skud/data/GBASE.FDB", user="SYSDBA", password="masterkey", charset="WIN1251")
gb_cur = gb.cursor()
gb_cur.execute("SELECT USERID FROM UPH WHERE PHOTO IS NOT NULL")
user_ids = [row[0] for row in gb_cur.fetchall()]
saved = 0
for fb_user_id in user_ids:
    try:
        cur2 = gb.cursor()
        cur2.execute("SELECT PHOTO FROM UPH WHERE USERID=?", (fb_user_id,))
        row = cur2.fetchone()
        if not row: continue
        blob = row[0]
        if hasattr(blob, 'read'):
            photo_data = b""
            chunk = blob.read(8192)
            while chunk:
                photo_data += chunk if isinstance(chunk, bytes) else chunk.encode('latin-1')
                chunk = blob.read(8192)
        else:
            photo_data = bytes(blob)
        tab = fb_id_to_tab.get(fb_user_id)
        our_id = tab_to_our.get(tab) if tab else None
        if not our_id or not photo_data: continue
        with open(f"{PHOTO_DIR}/{our_id}.jpg", "wb") as f:
            f.write(photo_data)
        our_db.execute("UPDATE employees SET photo=? WHERE id=?", (f"/photos/{our_id}.jpg", our_id))
        saved += 1
    except: pass
our_db.commit()
our_db.close()
gb.close()
print(f"Фото восстановлено: {saved}")
PYEOF

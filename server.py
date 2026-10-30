#!/usr/bin/env python3
"""سيرفر تانك TANK — بدون أي مكتبات خارجية (Python 3.8+ فقط).
يشغّل: قاعدة البيانات + واجهة API + صفحات التطبيق (مجلد public) في أمر واحد:  python server.py
"""
import hashlib, hmac, json, mimetypes, os, re, secrets, socket, sqlite3, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import config

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.realpath(os.path.join(BASE, "public"))
DB_PATH = os.path.join(BASE, config.DB_FILE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALERT_TYPES = {"crit", "warn", "danger", "pump", "good"}
DEFAULTS = {"tankHeight": 37, "deadZone": 20, "capacity": 35, "low": 40, "crit": 20,
            "repeatMin": 1, "vibrate": True, "suppliers": []}
NUM_RULES = {"tankHeight": (20, 1000), "deadZone": (0, 200), "capacity": (20, 100000),
             "low": (5, 90), "crit": (1, 80), "repeatMin": (1, 120)}
NOW = lambda: int(time.time() * 1000)
_login_fails = {}
_inserts = 0


class ApiError(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg


# ------------------------------------------------------------ قاعدة البيانات
def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def init_db():
    con = db()
    con.execute("PRAGMA journal_mode=WAL")
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    # تسجيل الحساس (الوهمي أو الحقيقي) من config.py
    row = con.execute("SELECT id FROM devices WHERE device_id=?", (config.DEVICE_ID,)).fetchone()
    if row:
        con.execute("UPDATE devices SET key_hash=? WHERE id=?", (sha(config.DEVICE_KEY), row["id"]))
    else:
        con.execute("INSERT INTO devices(device_id,key_hash,created_at) VALUES(?,?,?)",
                    (config.DEVICE_ID, sha(config.DEVICE_KEY), NOW()))
    con.execute("DELETE FROM readings WHERE ts<?", (NOW() - 30 * 86400 * 1000,))
    con.commit()
    con.close()


def secret():
    env = os.environ.get("TANK_SECRET")
    if env:
        return env.encode()
    path = os.path.join(BASE, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip().encode()


SECRET = None


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def make_token(uid):
    exp = int(time.time()) + config.SESSION_DAYS * 86400
    p = f"{uid}.{exp}"
    return f"{p}.{hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()}"


def auth(handler, con):
    h = handler.headers.get("Authorization", "")
    try:
        uid, exp, sig = (h[7:] if h.startswith("Bearer ") else h).strip().split(".")
        good = hmac.new(SECRET, f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, good) and int(exp) > time.time():
            u = con.execute("SELECT id,name,email FROM users WHERE id=?", (int(uid),)).fetchone()
            if u:
                return u
    except Exception:
        pass
    raise ApiError(401, "سجّل دخولك أولاً")


# ------------------------------------------------------------ الإعدادات
def user_settings(con, uid):
    s = dict(DEFAULTS)
    row = con.execute("SELECT data FROM settings WHERE user_id=?", (uid,)).fetchone()
    if row:
        s.update(json.loads(row["data"]))
    d = con.execute("SELECT device_id FROM devices WHERE user_id=? ORDER BY id LIMIT 1", (uid,)).fetchone()
    s["deviceId"] = d["device_id"] if d else ""
    return s


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x


def clean_settings(body, current):
    s = {k: current[k] for k in DEFAULTS}
    for k, (lo, hi) in NUM_RULES.items():
        if k in body:
            if not is_num(body[k]) or not lo <= body[k] <= hi:
                raise ApiError(400, f"قيمة غير صحيحة: {k}")
            s[k] = body[k]
    if "vibrate" in body:
        s["vibrate"] = bool(body["vibrate"])
    if "suppliers" in body:
        sup = body["suppliers"]
        if not isinstance(sup, list) or len(sup) > 20:
            raise ApiError(400, "قائمة الموردين غير صحيحة")
        out = []
        for x in sup:
            name, phone = str(x.get("name", "")).strip(), str(x.get("phone", "")).strip()
            if not name or not phone or len(name) > 60 or not re.fullmatch(r"[\d+\-\s()]{5,25}", phone):
                raise ApiError(400, "بيانات المورّد غير صحيحة (تأكد من الاسم والرقم)")
            out.append({"name": name, "phone": phone})
        s["suppliers"] = out
    if s["crit"] >= s["low"]:
        raise ApiError(400, "المستوى الحرج لازم يكون أقل من المنخفض")
    if s["deadZone"] >= s["tankHeight"]:
        raise ApiError(400, "المسافة الميتة لازم تكون أقل من ارتفاع الخزان")
    return s


def to_level(distance, level, s):
    if is_num(level):
        return max(0, min(100, round(level)))
    if is_num(distance):
        span = s["tankHeight"] - s["deadZone"]
        return max(0, min(100, round((s["tankHeight"] - distance) / span * 100)))
    return None



# ------------------------------------------------------------ لوحة الإدارة
ADMIN_SQL = {
    "users": ("SELECT u.id,u.name,u.email,u.created_at,(SELECT device_id FROM devices d WHERE d.user_id=u.id LIMIT 1) AS device,"
              "(SELECT COUNT(*) FROM alerts a WHERE a.user_id=u.id) AS alerts FROM users u", ("name", "email", "device")),
    "devices": ("SELECT d.id,d.device_id,u.name AS owner,u.email AS owner_email,(SELECT COUNT(*) FROM readings r WHERE r.device_id=d.device_id) AS readings,"
                "(SELECT MAX(ts) FROM readings r WHERE r.device_id=d.device_id) AS last_seen,d.created_at FROM devices d LEFT JOIN users u ON u.id=d.user_id",
                ("device_id", "owner", "owner_email")),
    "readings": ("SELECT id,device_id,ts,distance_cm,level,pump FROM readings", ("device_id",)),
    "alerts": ("SELECT a.id,u.name AS user,a.ts,a.type,a.msg FROM alerts a JOIN users u ON u.id=a.user_id", ("user", "type", "msg")),
    "settings": ("SELECT s.user_id AS id,u.name AS user,s.data FROM settings s JOIN users u ON u.id=s.user_id", ("user", "data")),
}


def admin_sig(exp):
    return hmac.new(SECRET, f"admin.{exp}".encode(), hashlib.sha256).hexdigest()


def check_admin(h):
    try:
        a, exp, sig = (h.headers.get("Authorization", "")[7:]).split(".")
        if a == "a" and int(exp) > time.time() and hmac.compare_digest(sig, admin_sig(exp)):
            return
    except Exception:
        pass
    raise ApiError(401, "سجّل دخول المدير أولاً")


def admin_route(h, con, method, path, q, body):
    if path == "/admin/login" and method == "POST":
        k = (h.client_address[0], "admin")
        fails = [t for t in _login_fails.get(k, []) if t > time.time() - 300]
        if len(fails) >= 6:
            raise ApiError(429, "محاولات كثيرة، انتظر 5 دقائق")
        if not hmac.compare_digest(str(body.get("password", "")).encode(), config.ADMIN_PASSWORD.encode()):
            _login_fails[k] = fails + [time.time()]
            raise ApiError(401, "كلمة مرور المدير غير صحيحة")
        exp = int(time.time()) + 8 * 3600
        return {"token": f"a.{exp}.{admin_sig(exp)}"}
    check_admin(h)
    if path == "/admin/overview":
        return {t: con.execute(f"SELECT COUNT(*) FROM ({ADMIN_SQL[t][0]})").fetchone()[0] for t in ADMIN_SQL}
    m = re.fullmatch(r"/admin/table/(\w+)", path)
    if m and method == "GET":
        if m.group(1) not in ADMIN_SQL:
            raise ApiError(404, "الجدول غير موجود")
        sql, cols = ADMIN_SQL[m.group(1)]
        text = q.get("q", [""])[0].strip()[:80]
        try:
            page = max(1, int(q.get("page", ["1"])[0]))
        except ValueError:
            page = 1
        where, args = "", []
        if text:
            where = " WHERE " + " OR ".join(f"CAST({c} AS TEXT) LIKE ?" for c in cols)
            args = [f"%{text}%"] * len(cols)
        total = con.execute(f"SELECT COUNT(*) FROM ({sql}){where}", args).fetchone()[0]
        cur = con.execute(f"SELECT * FROM ({sql}){where} ORDER BY id DESC LIMIT 50 OFFSET ?", args + [(page - 1) * 50])
        return {"columns": [d[0] for d in cur.description], "rows": [list(r) for r in cur.fetchall()], "total": total, "page": page, "per": 50}
    m = re.fullmatch(r"/admin/users/(\d+)", path)
    if m and method == "DELETE":
        con.execute("DELETE FROM users WHERE id=?", (int(m.group(1)),))
        return {"ok": True}
    m = re.fullmatch(r"/admin/devices/(\d+)/unlink", path)
    if m and method == "POST":
        con.execute("UPDATE devices SET user_id=NULL WHERE id=?", (int(m.group(1)),))
        return {"ok": True}
    raise ApiError(404, "المسار غير موجود")

# ------------------------------------------------------------ المسارات
def dispatch(h, con, method, path, q, body):
    global _inserts
    if path == "/health":
        return {"ok": True}

    if path == "/sensor/reading" and method == "POST":          # من الحساس (ESP32)
        did = str(body.get("deviceId", "")).strip()
        dev = con.execute("SELECT device_id,key_hash FROM devices WHERE device_id=?", (did,)).fetchone()
        key = h.headers.get("X-Device-Key", "")
        if not dev or not hmac.compare_digest(dev["key_hash"], sha(key)):
            raise ApiError(401, "رقم الجهاز أو المفتاح غير صحيح")
        dist, lvl = body.get("distance_cm"), body.get("level")
        if not (is_num(dist) and 0 <= dist <= 1000) and not (is_num(lvl) and 0 <= lvl <= 100):
            raise ApiError(400, "أرسل distance_cm (0-1000) أو level (0-100)")
        pump = 1 if body.get("pump") in (True, 1, "1", "true", "on") else 0
        con.execute("INSERT INTO readings(device_id,ts,distance_cm,level,pump) VALUES(?,?,?,?,?)",
                    (dev["device_id"], NOW(), dist if is_num(dist) else None, lvl if is_num(lvl) else None, pump))
        _inserts += 1
        if _inserts % 1000 == 0:
            con.execute("DELETE FROM readings WHERE ts<?", (NOW() - 30 * 86400 * 1000,))
        return {"ok": True}

    if path == "/auth/register" and method == "POST":
        name, email, pw = str(body.get("name", "")).strip(), str(body.get("email", "")).strip().lower(), str(body.get("password", ""))
        if not 1 <= len(name) <= 60:
            raise ApiError(400, "اكتب اسمك")
        if not EMAIL_RE.match(email) or len(email) > 120:
            raise ApiError(400, "البريد الإلكتروني غير صحيح")
        if not 6 <= len(pw) <= 200:
            raise ApiError(400, "كلمة المرور لازم تكون 6 أحرف على الأقل")
        if con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise ApiError(409, "هذا البريد مسجّل من قبل")
        salt = secrets.token_hex(16)
        uid = con.execute("INSERT INTO users(name,email,password_hash,salt,created_at) VALUES(?,?,?,?,?)",
                          (name, email, hash_pw(pw, salt), salt, NOW())).lastrowid
        return {"token": make_token(uid), "user": {"name": name, "email": email}}

    if path == "/auth/login" and method == "POST":
        email, pw = str(body.get("email", "")).strip().lower(), str(body.get("password", ""))
        k = (h.client_address[0], email)
        fails = [t for t in _login_fails.get(k, []) if t > time.time() - 300]
        if len(fails) >= 8:
            raise ApiError(429, "محاولات كثيرة، انتظر 5 دقائق ثم حاول")
        u = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not u or not hmac.compare_digest(u["password_hash"], hash_pw(pw, u["salt"])):
            _login_fails[k] = fails + [time.time()]
            raise ApiError(401, "البريد أو كلمة المرور غير صحيحة")
        _login_fails.pop(k, None)
        return {"token": make_token(u["id"]), "user": {"name": u["name"], "email": u["email"]}}

    if path.startswith("/admin/"):
        return admin_route(h, con, method, path, q, body)

    user = auth(h, con)          # كل ما تحت يحتاج تسجيل دخول
    uid = user["id"]

    if path == "/settings":
        if method == "PUT":
            s = clean_settings(body, user_settings(con, uid))
            con.execute("INSERT INTO settings(user_id,data) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                        (uid, json.dumps(s, ensure_ascii=False)))
        return user_settings(con, uid)

    if path == "/device/link" and method == "POST":
        did = str(body.get("deviceId", "")).strip()
        con.execute("UPDATE devices SET user_id=NULL WHERE user_id=?", (uid,))
        if did:
            dev = con.execute("SELECT * FROM devices WHERE device_id=?", (did,)).fetchone()
            if not dev:
                raise ApiError(404, "رقم الجهاز غير موجود، تأكد من الرقم")
            if dev["user_id"] and dev["user_id"] != uid:
                raise ApiError(409, "هذا الجهاز مرتبط بحساب آخر")
            con.execute("UPDATE devices SET user_id=? WHERE id=?", (uid, dev["id"]))
        return {"ok": True}

    if path in ("/tank/latest", "/tank/history") and method == "GET":
        s = user_settings(con, uid)
        if not s["deviceId"]:
            raise ApiError(404, "لم تربط جهاز حساس بعد")
        if path == "/tank/latest":
            r = con.execute("SELECT * FROM readings WHERE device_id=? ORDER BY ts DESC LIMIT 1", (s["deviceId"],)).fetchone()
            if not r:
                raise ApiError(404, "لا توجد قراءات من الجهاز بعد")
            return {"deviceId": r["device_id"], "ts": r["ts"], "distance_cm": r["distance_cm"], "level": r["level"], "pump": bool(r["pump"])}
        try:
            hours = max(1, min(720, int(q.get("hours", ["24"])[0])))
        except ValueError:
            hours = 24
        rows = con.execute("SELECT ts,distance_cm,level FROM readings WHERE device_id=? AND ts>? ORDER BY ts",
                           (s["deviceId"], NOW() - hours * 3600 * 1000)).fetchall()
        pts = [{"ts": r["ts"], "level": lv} for r in rows if (lv := to_level(r["distance_cm"], r["level"], s)) is not None]
        step = max(1, len(pts) // 300)
        return pts[::step]

    if path == "/alerts":
        if method == "POST":
            t, msg = body.get("type"), str(body.get("msg", "")).strip()[:300]
            if t not in ALERT_TYPES or not msg:
                raise ApiError(400, "تنبيه غير صحيح")
            ts = body.get("ts") if is_num(body.get("ts")) else NOW()
            con.execute("INSERT INTO alerts(user_id,ts,type,msg) VALUES(?,?,?,?)", (uid, int(ts), t, msg))
            con.execute("DELETE FROM alerts WHERE user_id=? AND id NOT IN (SELECT id FROM alerts WHERE user_id=? ORDER BY ts DESC LIMIT 200)", (uid, uid))
            return {"ok": True}
        if method == "DELETE":
            con.execute("DELETE FROM alerts WHERE user_id=?", (uid,))
            return {"ok": True}
        return [dict(r) for r in con.execute("SELECT ts,type,msg FROM alerts WHERE user_id=? ORDER BY ts DESC LIMIT 100", (uid,))]

    raise ApiError(404, "المسار غير موجود")


# ------------------------------------------------------------ السيرفر
class Handler(BaseHTTPRequestHandler):
    server_version = "TankServer"

    def log_message(self, *a):
        pass

    def send_bytes(self, code, data, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, code, obj):
        self.send_bytes(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 65536:
            raise ApiError(413, "الطلب كبير")
        if n == 0:
            return {}
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            raise ApiError(400, "صيغة JSON غير صحيحة")
        if not isinstance(d, dict):
            raise ApiError(400, "صيغة JSON غير صحيحة")
        return d

    def api(self, method):
        u = urlparse(self.path)
        try:
            body = self.read_json() if method in ("POST", "PUT") else {}
            con = db()
            try:
                data = dispatch(self, con, method, u.path[4:] or "/", parse_qs(u.query), body)
                con.commit()
            finally:
                con.close()
            self.send_json(200, data)
        except ApiError as e:
            self.send_json(e.code, {"message": e.msg})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"message": "خطأ في السيرفر"})

    def static(self):
        p = unquote(urlparse(self.path).path)
        if p.endswith("/"):
            p += "index.html"
        if p == "/admin":
            p = "/admin.html"
        full = os.path.realpath(os.path.join(PUBLIC, p.lstrip("/")))
        if not full.startswith(PUBLIC + os.sep) or not os.path.isfile(full):
            return self.send_bytes(404, "غير موجود".encode(), "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self.send_bytes(200, f.read(), ctype, {"Cache-Control": "no-cache"})

    def route(self, method):
        if self.path.startswith("/api/") or self.path == "/api":
            return self.api(method)
        if method == "GET":
            return self.static()
        self.send_json(405, {"message": "الطريقة غير مسموحة"})

    def do_GET(self): self.route("GET")
    def do_POST(self): self.route("POST")
    def do_PUT(self): self.route("PUT")
    def do_DELETE(self): self.route("DELETE")


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    SECRET = secret()
    init_db()
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    ip = lan_ip()
    print("=" * 56)
    print(" تانك TANK يعمل ✅")
    print(f"  على هذا الجهاز:   http://localhost:{config.PORT}")
    print(f"  من الجوال (نفس الواي فاي): http://{ip}:{config.PORT}")
    print(f"  عنوان الحساس (ESP32):  http://{ip}:{config.PORT}/api/sensor/reading")
    print(f"  رقم الحساس: {config.DEVICE_ID}")
    print(f"  لوحة الإدارة:  http://localhost:{config.PORT}/admin")
    if config.ADMIN_PASSWORD == "admin12345":
        print("  ⚠ كلمة مرور المدير الافتراضية — غيّرها في config.py")
    if config.DEVICE_KEY.startswith("CHANGE-ME"):
        print("  ⚠ تستخدم بيانات حساس وهمية — غيّرها في config.py لما يوصلك الحساس")
    print("  للإيقاف: Ctrl+C")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nتم الإيقاف.")

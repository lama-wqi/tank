-- قاعدة بيانات تانك TANK (SQLite) — تُنشأ تلقائياً عند أول تشغيل
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT    NOT NULL,
  email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT    NOT NULL,           -- PBKDF2-SHA256، لا تُحفظ كلمة المرور نفسها
  salt          TEXT    NOT NULL,
  created_at    INTEGER NOT NULL            -- ملي ثانية
);

CREATE TABLE IF NOT EXISTS devices (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id  TEXT    NOT NULL UNIQUE COLLATE NOCASE,   -- مثل TANK-0001
  key_hash   TEXT    NOT NULL,                         -- SHA-256 لمفتاح الجهاز
  user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS readings (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id   TEXT    NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
  ts          INTEGER NOT NULL,             -- وقت وصول القراءة (ملي ثانية)
  distance_cm REAL,                         -- المسافة من الحساس لسطح الماء
  level       REAL,                         -- أو نسبة جاهزة 0-100
  pump        INTEGER NOT NULL DEFAULT 0    -- 1 = الدينمو يعمل
);
CREATE INDEX IF NOT EXISTS idx_readings_dev_ts ON readings(device_id, ts);

CREATE TABLE IF NOT EXISTS settings (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  data    TEXT NOT NULL                     -- JSON: أبعاد الخزان، حدود التنبيه، الموردين
);

CREATE TABLE IF NOT EXISTS alerts (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ts      INTEGER NOT NULL,
  type    TEXT    NOT NULL,                 -- crit | warn | danger | pump | good
  msg     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_user_ts ON alerts(user_id, ts);

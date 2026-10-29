#!/usr/bin/env python3
"""حساس وهمي: يرسل قراءات للسيرفر مثل ما بيسوي حساسك الحقيقي.
التشغيل (والسيرفر شغّال):   python simulate_sensor.py
خيارات:  --interval 2   (ثواني بين القراءات)   --start 60   (النسبة الابتدائية)
"""
import argparse, json, time, urllib.error, urllib.request

import config

p = argparse.ArgumentParser()
p.add_argument("--url", default=f"http://localhost:{config.PORT}/api/sensor/reading")
p.add_argument("--interval", type=float, default=3)
p.add_argument("--start", type=float, default=85)
a = p.parse_args()

TANK_HEIGHT, DEAD_ZONE = 150, 20      # لازم تطابق إعدادات الخزان في التطبيق
level = a.start
print(f"إرسال قراءات وهمية للحساس {config.DEVICE_ID} إلى {a.url}  (Ctrl+C للإيقاف)")
while True:
    level = 100.0 if level <= 3 else level - 1.0
    pump = int(level) // 10 % 2 == 0
    distance = DEAD_ZONE + (1 - level / 100) * (TANK_HEIGHT - DEAD_ZONE)
    data = json.dumps({"deviceId": config.DEVICE_ID, "distance_cm": round(distance, 1), "pump": pump}).encode()
    req = urllib.request.Request(a.url, data, {"Content-Type": "application/json", "X-Device-Key": config.DEVICE_KEY})
    try:
        urllib.request.urlopen(req, timeout=5).read()
        print(f"✔ المستوى {level:.0f}%  المسافة {distance:.1f} سم  الدينمو {'يعمل' if pump else 'متوقف'}")
    except urllib.error.HTTPError as e:
        print("✘ رفض السيرفر:", e.read().decode("utf-8", "ignore"))
    except Exception as e:
        print("✘ تعذّر الاتصال:", e)
    time.sleep(a.interval)

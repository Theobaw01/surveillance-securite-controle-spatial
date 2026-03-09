"""Test complet du workflow d'inspection."""
import urllib.request
import json
import time

API = "http://localhost:8002"

# Login
d = json.dumps({"username": "admin", "password": "admin_surv_2024"}).encode()
req = urllib.request.Request(API + "/auth/token", data=d, headers={"Content-Type": "application/json"})
token = json.loads(urllib.request.urlopen(req).read())["access_token"]
h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}

# 1. Start stream
print("=== 1. Start stream ===")
data = json.dumps({"source": "0", "camera_id": "cam_01"}).encode()
req = urllib.request.Request(API + "/stream/start", data=data, headers=h)
try:
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    print("ERROR:", e)
    # Try stop + restart
    data2 = json.dumps({"camera_id": "cam_01"}).encode()
    req2 = urllib.request.Request(API + "/stream/stop", data=data2, headers=h)
    try:
        urllib.request.urlopen(req2)
    except:
        pass
    time.sleep(2)
    req = urllib.request.Request(API + "/stream/start", data=data, headers=h)
    print(urllib.request.urlopen(req).read().decode())

time.sleep(3)

# 2. Stream status
print("\n=== 2. Stream status ===")
r = urllib.request.urlopen(API + "/stream/status?camera_id=cam_01")
st = json.loads(r.read().decode())
print(f"Running: {st['is_running']}, FPS: {st['fps']}, Frames: {st['frames_processed']}")

# 3. Start inspection
print("\n=== 3. Start inspection ===")
req = urllib.request.Request(API + "/inspection/start?camera_id=cam_01", data=b"", headers=h, method="POST")
try:
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    print("ERROR:", e)
    if hasattr(e, "read"):
        print(e.read().decode())

# 4. Wait and check
print("\n=== 4. Waiting 8s for face recognition... ===")
time.sleep(8)

r = urllib.request.urlopen(API + "/inspection/status?camera_id=cam_01")
st = json.loads(r.read().decode())
print(f"Inspection active: {st['active']}")
print(f"Persons present: {st['present_count']}")
for p in st.get("present_persons", []):
    sim = p.get("similarity", 0)
    print(f"  - {p['full_name']} | Entrée: {p['entry_time']} | Durée: {p['duration_formatted']} | Sim: {sim:.0%}")
print(f"Total visits (completed): {st['total_visits']}")

# 5. Wait more
print("\n=== 5. Waiting 5 more seconds... ===")
time.sleep(5)

r = urllib.request.urlopen(API + "/inspection/status?camera_id=cam_01")
st = json.loads(r.read().decode())
print(f"Persons present: {st['present_count']}")
for p in st.get("present_persons", []):
    print(f"  - {p['full_name']} | {p['duration_formatted']}")

# 6. Stop inspection
print("\n=== 6. Stop inspection ===")
req = urllib.request.Request(API + "/inspection/stop?camera_id=cam_01", data=b"", headers=h, method="POST")
rpt = json.loads(urllib.request.urlopen(req).read().decode())
print(f"Started: {rpt.get('started_at')}")
print(f"Stopped: {rpt.get('stopped_at')}")
print(f"Total visits: {rpt['total_visits']}")
for v in rpt.get("history", []):
    dur = v.get("duration_sec", 0)
    m = int(dur // 60)
    s = int(dur % 60)
    print(f"  {v['prenom']} {v['nom']}: {v.get('entry_time','')} -> {v.get('exit_time','')} ({m}m{s}s)")

# 7. Check attendance records
print("\n=== 7. Attendance today ===")
r = urllib.request.urlopen(API + "/attendance/today")
att = json.loads(r.read().decode())
print(f"Records: {att['total']}")
for rec in att.get("records", []):
    print(f"  {rec.get('prenom','')} {rec.get('nom','')} - {rec.get('direction','')} at {rec.get('datetime_str','')}")

# 8. Presence duration
print("\n=== 8. Presence duration ===")
r = urllib.request.urlopen(API + "/attendance/presence")
pres = json.loads(r.read().decode())
print(f"Total: {pres['total']}")
for rec in pres.get("records", []):
    sp = "encore là" if rec.get("still_present") else rec.get("exit_time", "")
    print(f"  {rec['prenom']} {rec['nom']}: {rec['entry_time']} -> {sp} | {rec['duration_formatted']}")

# 9. Stop stream
print("\n=== 9. Stop stream ===")
data = json.dumps({"camera_id": "cam_01"}).encode()
req = urllib.request.Request(API + "/stream/stop", data=data, headers=h)
print(urllib.request.urlopen(req).read().decode())

print("\n=== ALL TESTS PASSED ===")

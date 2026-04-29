import os
import cv2
from ultralytics import YOLO
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import requests
import datetime
import sqlite3

# Cấu hình đường dẫn
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
DB_PATH = os.path.join(BASE_DIR, "violations.db")
MODEL_PATH = os.path.join(BASE_DIR, "best.pt")

# --- CẤU HÌNH TELEGRAM ---
TOKEN = "8771128025:AAETjmbKU_3D2TpnxGJ1cuL1vtZhXexi7RM"
CHAT_ID = "6149437756"

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)
model = YOLO(MODEL_PATH)

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS violations 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       time TEXT, type TEXT, staff_name TEXT, location TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       fullname TEXT, username TEXT UNIQUE, password TEXT)''')
    # BẢNG MỚI: QUẢN LÝ THIẾT BỊ CAMERA
    cursor.execute('''CREATE TABLE IF NOT EXISTS cameras 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       name TEXT, url TEXT)''')
    conn.commit()
    conn.close()

setup_db()

# --- CAMERA AI (ĐÃ NÂNG CẤP ĐỂ CHẠY NHIỀU CAMERA CÙNG LÚC) ---
def generate_frames(camera_url):
    # Nhận diện nếu nhập "0" thì mở Webcam, nếu nhập link RTSP thì mở camera quán
    source = int(camera_url) if str(camera_url).isdigit() else camera_url
    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW if str(camera_url).isdigit() else cv2.CAP_ANY)
    
    last_alert_time = datetime.datetime.now() - datetime.timedelta(seconds=30)
    
    while True:
        success, frame = cap.read()
        if not success: break
        
        results = model(frame, verbose=False)
        violation_detected = False
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) == 0: 
                    violation_detected = True
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(frame, "VI PHAM", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        
        if violation_detected:
            now = datetime.datetime.now()
            if (now - last_alert_time).seconds > 20:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO violations (time, type, staff_name, location) VALUES (?, ?, ?, ?)", 
                               (now.strftime('%Y-%m-%d %H:%M:%S'), "Không đeo khẩu trang", "NV. Bếp", f"Camera {source}"))
                conn.commit()
                conn.close()
                
                # Gửi Telegram
                url_tele = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
                _, img_encoded = cv2.imencode('.jpg', frame)
                files = {'photo': ('vi-pham.jpg', img_encoded.tobytes())}
                data = {'chat_id': CHAT_ID, 'caption': f"⚠️ VIETFOOD GUARD: Phát hiện vi phạm!\nNguồn: Camera {source}\nThời gian: {now.strftime('%H:%M:%S')}"}
                try: requests.post(url_tele, data=data, files=files, timeout=5)
                except: pass
                last_alert_time = now

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# --- API QUẢN LÝ CAMERA DÀNH CHO KHÁCH HÀNG ---

@app.get("/get_cameras")
def get_cameras():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/add_camera")
async def add_camera(name: str = Form(...), url: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cameras (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/delete_camera/{cam_id}")
def delete_camera(cam_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cameras WHERE id = ?", (cam_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

# Đây là bộ phát video dành riêng cho từng ID camera
@app.get("/video_feed/{cam_id}")
def video_feed_id(cam_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM cameras WHERE id = ?", (cam_id,))
    res = cursor.fetchone()
    conn.close()
    url = res[0] if res else "0"
    return StreamingResponse(generate_frames(url), media_type="multipart/x-mixed-replace; boundary=frame")

# (Giữ lại link cũ phòng trường hợp html chưa cập nhật)
@app.get("/video_feed")
def video_feed_default():
    return StreamingResponse(generate_frames("0"), media_type="multipart/x-mixed-replace; boundary=frame")


# --- ROUTING CƠ BẢN ---

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="hom.html")

@app.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
async def login_post(username: str = Form(...), password: str = Form(...)):
    if username == "admin@vietfood.vn" and password == "12345678":
        return RedirectResponse(url="/dashboard", status_code=303)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login?error=1", status_code=303)

@app.post("/register")
async def register(fullname: str = Form(...), username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (fullname, username, password) VALUES (?, ?, ?)", (fullname, username, password))
        conn.commit()
    except: pass
    finally: conn.close()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM violations WHERE time LIKE ?", (f'{today}%',))
    total_today = cursor.fetchone()[0]
    cursor.execute("SELECT * FROM violations ORDER BY id DESC LIMIT 5")
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"total_today": total_today, "history": history}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
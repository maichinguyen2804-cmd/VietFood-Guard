import os
import cv2
from ultralytics import YOLO
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
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
templates = Jinja2Templates(directory=TEMPLATE_DIR)
model = YOLO(MODEL_PATH)

# 1. Khởi tạo Database với các cột chi tiết (Tên NV, Vị trí)
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS violations 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       time TEXT, 
                       type TEXT, 
                       staff_name TEXT, 
                       location TEXT)''')
    conn.commit()
    conn.close()

setup_db()

def send_telegram_alert(frame):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    _, img_encoded = cv2.imencode('.jpg', frame)
    files = {'photo': ('vi-pham.jpg', img_encoded.tobytes())}
    data = {'chat_id': CHAT_ID, 'caption': f"⚠️ VIETFOOD GUARD: Phát hiện vi phạm!\nThời gian: {datetime.datetime.now().strftime('%H:%M:%S')}"}
    try:
        requests.post(url, data=data, files=files, timeout=5)
    except:
        pass

def generate_frames():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
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
                # Lưu thông tin chi tiết vào DB
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""INSERT INTO violations (time, type, staff_name, location) 
                                  VALUES (?, ?, ?, ?)""", 
                               (now.strftime('%Y-%m-%d %H:%M:%S'), 
                                "Không đeo khẩu trang", 
                                "NV. Nguyễn Văn A", # Sau này bạn có thể thay bằng nhận diện khuôn mặt
                                "Khu sơ chế"))
                conn.commit()
                conn.close()
                send_telegram_alert(frame)
                last_alert_time = now

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# --- PHẦN ĐIỀU HƯỚNG GIAO DIỆN WEB APP ---

@app.get("/")
async def home_page(request: Request):
    # Trang giới thiệu (Cái vỏ)
    return templates.TemplateResponse(request=request, name="hom.html")

@app.get("/login")
async def login_page(request: Request):
    # Trang đăng nhập mới thêm
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/dashboard")
async def dashboard_page(request: Request):
    # Trang Dashboard quản lý camera (Cái lõi)
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

# API lấy dữ liệu thống kê để hiển thị lên Dashboard
@app.get("/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # Đếm số ca vi phạm hôm nay
    cursor.execute("SELECT COUNT(*) FROM violations WHERE time LIKE ?", (f'{today}%',))
    total_today = cursor.fetchone()[0]
    
    # Lấy 5 ca vi phạm mới nhất
    cursor.execute("SELECT * FROM violations ORDER BY id DESC LIMIT 5")
    history = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return {"total_today": total_today, "history": history}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
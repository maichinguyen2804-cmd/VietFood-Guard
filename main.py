import cv2
from ultralytics import YOLO
import datetime
import os
import requests
import winsound 

# --- THÔNG TIN ĐÃ CẤU HÌNH XONG ---
TOKEN = "8771128025:AAHDvnD_geDQFeE53AMvyY4IX-U4eOvn9GQ"
CHAT_ID = "6149437756" 

# Tải mô hình nhận diện của bạn
model = YOLO('best.pt') 

# Tạo thư mục lưu ảnh vi phạm nếu chưa có
if not os.path.exists('canh_bao_vi_pham'):
    os.makedirs('canh_bao_vi_pham')

def send_telegram_photo(photo_path):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        payload = {
            "chat_id": CHAT_ID, 
            "caption": f"⚠️ VIETFOOD GUARD: Phát hiện nhân viên vi phạm! \nThời gian: {datetime.datetime.now().strftime('%H:%M:%S')}"
        }
        files = {"photo": photo}
        try:
            requests.post(url, data=payload, files=files)
            print("--- Đã gửi cảnh báo tới Telegram thành công! ---")
        except:
            print("Lỗi: Không thể gửi ảnh. Kiểm tra lại kết nối mạng!")

cap = cv2.VideoCapture(0)
last_alert_time = datetime.datetime.now()

print("Hệ thống VietFood Guard đang khởi động...")

while cap.isOpened():
    success, frame = cap.read()
    if success:
        results = model(frame)
        annotated_frame = frame.copy()
        violation_detected = False

        for r in results:
            for box in r.boxes:
                class_id = int(box.cls[0])
                label = model.names[class_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                if label == 'face': # Nhãn vi phạm (không khẩu trang)
                    color = (0, 0, 255) # Màu đỏ
                    violation_detected = True
                    cv2.putText(annotated_frame, "VI PHAM!", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                else: # Nhãn hợp lệ
                    color = (0, 255, 0) # Màu xanh lá
                    cv2.putText(annotated_frame, "HOP LE", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

        # Xử lý khi phát hiện không đeo khẩu trang
        if violation_detected:
            current_time = datetime.datetime.now()
            # 15 giây gửi 1 lần để tránh spam tin nhắn
            if (current_time - last_alert_time).seconds > 15:
                print("⚠️ Phát hiện vi phạm! Đang gửi cảnh báo...")
                winsound.Beep(1000, 500) # Phát tiếng kêu báo động tại chỗ
                
                # Lưu ảnh và gửi đi
                img_name = f"vi_pham_{current_time.strftime('%H%M%S')}.jpg"
                img_path = os.path.join('canh_bao_vi_pham', img_name)
                cv2.imwrite(img_path, frame)
                
                send_telegram_photo(img_path)
                last_alert_time = current_time

        cv2.imshow("VIETFOOD GUARD - HE THONG GIAM SAT AN TOAN", annotated_frame)
        
        # Nhấn phím 'q' để thoát
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()
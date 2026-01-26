# 🚀 Quick Start Guide

## Bắt đầu nhanh trong 3 bước

### Bước 1: Cài đặt (chỉ cần làm 1 lần)

```bash
# Chạy file setup
setup_venv.bat
```

✅ Script này sẽ tự động:
- Tạo môi trường ảo Python
- Cài đặt tất cả thư viện cần thiết

### Bước 2: Khởi động MongoDB

**Cách 1: Dùng MongoDB Compass**
- Mở MongoDB Compass
- Connect to `mongodb://localhost:27017`

**Cách 2: Dùng Command Line**
```bash
net start MongoDB
```

### Bước 3: Chạy ứng dụng

```bash
# Chạy file run
run.bat
```

Mở trình duyệt: **http://localhost:5000**

---

## 📱 Hướng dẫn sử dụng

### 1️⃣ Đăng ký tài khoản
- Click "Đăng ký ngay"
- Nhập: username, email, password
- Click "Đăng ký"

### 2️⃣ Đăng nhập
- Nhập email và password
- Click "Đăng nhập"

### 3️⃣ Đăng ký khuôn mặt

**Dùng Camera:**
1. Click "Bật Camera"
2. Nhập tên người
3. Click "Chụp & Đăng ký"

**Dùng ảnh:**
1. Nhập tên người
2. Click "Chọn ảnh"
3. Click "Upload & Đăng ký"

### 4️⃣ Nhận diện RTSP
1. Nhập RTSP URL
   - Ví dụ: `rtsp://192.168.1.100:554/stream`
   - Hoặc test với: `0` (webcam)
2. Click "Bắt đầu"
3. Xem kết quả bên phải

---

## ⚡ Lưu ý quan trọng

### ✅ Yêu cầu
- Python 3.8+
- MongoDB đang chạy
- Webcam (cho đăng ký khuôn mặt)

### 🔧 Khắc phục lỗi

**Lỗi: "Error connecting to MongoDB"**
→ Khởi động MongoDB service

**Lỗi: "Không thể truy cập camera"**
→ Cho phép browser truy cập camera

**Lỗi: "Failed to open RTSP stream"**
→ Kiểm tra RTSP URL đúng định dạng

---

## 📂 Cấu trúc thư mục

```
attendence_app/
├── facedet/          # Models AI
├── models/           # Data models
├── services/         # Business logic
├── static/           # CSS, JS
├── templates/        # HTML
├── uploads/          # Ảnh đã đăng ký
├── app.py           # Ứng dụng chính
└── requirements.txt  # Dependencies
```

---

## 🎯 Tính năng chính

✅ Đăng ký/Đăng nhập an toàn
✅ Đăng ký khuôn mặt (camera/upload)
✅ Nhận diện RTSP real-time
✅ Lưu trữ MongoDB
✅ Giao diện đẹp, hiện đại

---

## 📞 Cần hỗ trợ?

1. Kiểm tra MongoDB đang chạy
2. Xem log trong terminal
3. Kiểm tra browser console (F12)
4. Đọc README.md để biết chi tiết

---

**Chúc bạn sử dụng thành công! 🎉**

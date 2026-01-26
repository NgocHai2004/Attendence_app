# 🎯 Hệ thống điểm danh nhận diện khuôn mặt

Hệ thống điểm danh thông minh sử dụng công nghệ nhận diện khuôn mặt với Flask, MongoDB và FaceNet.

## ✨ Tính năng

- 🔐 **Xác thực người dùng**: Đăng ký và đăng nhập an toàn
- 📸 **Đăng ký khuôn mặt**: Sử dụng camera hoặc upload ảnh
- 📹 **Nhận diện RTSP**: Nhận diện khuôn mặt từ RTSP stream
- 💾 **Lưu trữ MongoDB**: Quản lý dữ liệu người dùng và khuôn mặt
- 🎨 **Giao diện hiện đại**: Thiết kế đẹp mắt với glassmorphism

## 🛠️ Công nghệ sử dụng

- **Backend**: Flask, Python 3.8+
- **Database**: MongoDB
- **AI/ML**: TensorFlow Lite (FaceNet), ONNX Runtime
- **Computer Vision**: OpenCV
- **Frontend**: HTML5, CSS3, JavaScript

## 📋 Yêu cầu hệ thống

- Python 3.8 trở lên
- MongoDB (đang chạy trên localhost:27017)
- Webcam (cho chức năng đăng ký khuôn mặt)
- RTSP camera URL (tùy chọn)

## 🚀 Cài đặt

### Bước 1: Cài đặt môi trường ảo

Chạy file `setup_venv.bat`:

```bash
setup_venv.bat
```

Script này sẽ:
- Tạo môi trường ảo Python
- Cài đặt tất cả dependencies từ `requirements.txt`

### Bước 2: Cài đặt MongoDB

Nếu chưa có MongoDB, tải và cài đặt từ: https://www.mongodb.com/try/download/community

Khởi động MongoDB service:

```bash
# Windows
net start MongoDB

# Hoặc sử dụng MongoDB Compass
```

### Bước 3: Cấu hình

Kiểm tra file `.env` và điều chỉnh nếu cần:

```env
MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=attendance_db
SECRET_KEY=your-secret-key-change-this-in-production
FLASK_ENV=development
```

### Bước 4: Chạy ứng dụng

Chạy file `run.bat`:

```bash
run.bat
```

Hoặc chạy thủ công:

```bash
# Kích hoạt môi trường ảo
venv\Scripts\activate

# Chạy ứng dụng
python app.py
```

## 🌐 Sử dụng

1. Mở trình duyệt và truy cập: `http://localhost:5000`

2. **Đăng ký tài khoản**:
   - Click "Đăng ký ngay"
   - Nhập thông tin: username, email, password
   - Click "Đăng ký"

3. **Đăng nhập**:
   - Nhập email và password
   - Click "Đăng nhập"

4. **Đăng ký khuôn mặt**:
   
   **Cách 1: Sử dụng Camera**
   - Click "Bật Camera"
   - Nhập tên người
   - Click "Chụp & Đăng ký"
   
   **Cách 2: Upload ảnh**
   - Nhập tên người
   - Click "Chọn ảnh"
   - Chọn file ảnh
   - Click "Upload & Đăng ký"

5. **Nhận diện RTSP Stream**:
   - Nhập RTSP URL (ví dụ: `rtsp://192.168.1.100:554/stream`)
   - Click "Bắt đầu"
   - Xem kết quả nhận diện ở bên phải

## 📁 Cấu trúc thư mục

```
attendence_app/
├── facedet/                    # Models AI
│   ├── facedet.onnx           # Face detection model
│   ├── facenet.tflite         # Face encoding model
│   └── landmarkdet.yaml       # Landmark detection
├── models/                     # Data models
│   ├── user.py                # User model
│   └── face.py                # Face model
├── services/                   # Business logic
│   ├── database_service.py    # MongoDB operations
│   ├── face_recognition_service.py  # Face recognition
│   └── rtsp_service.py        # RTSP streaming
├── static/                     # Frontend assets
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── auth.js
│       └── dashboard.js
├── templates/                  # HTML templates
│   ├── login.html
│   ├── register.html
│   └── dashboard.html
├── uploads/                    # Uploaded images
├── app.py                      # Main Flask app
├── requirements.txt            # Python dependencies
├── .env                        # Environment config
├── setup_venv.bat             # Setup script
├── run.bat                     # Run script
└── README.md                   # This file
```

## 🔧 API Endpoints

### Authentication
- `POST /api/register` - Đăng ký người dùng mới
- `POST /api/login` - Đăng nhập
- `GET /api/logout` - Đăng xuất

### Face Registration
- `POST /api/register-face-camera` - Đăng ký khuôn mặt từ camera
- `POST /api/register-face-upload` - Đăng ký khuôn mặt từ upload
- `GET /api/faces` - Lấy danh sách khuôn mặt

### Recognition
- `POST /api/start-rtsp` - Bắt đầu RTSP stream
- `GET /api/stop-rtsp` - Dừng RTSP stream
- `GET /api/video-feed` - Video feed
- `GET /api/recognized-faces` - Danh sách khuôn mặt được nhận diện

## 🐛 Xử lý lỗi

### Lỗi kết nối MongoDB
```
Error connecting to MongoDB
```
**Giải pháp**: Đảm bảo MongoDB đang chạy

### Lỗi không tìm thấy model
```
Face detector not found
```
**Giải pháp**: Kiểm tra thư mục `facedet/` có đầy đủ file model

### Lỗi camera
```
Không thể truy cập camera
```
**Giải pháp**: 
- Cho phép trình duyệt truy cập camera
- Sử dụng HTTPS hoặc localhost

### Lỗi RTSP
```
Failed to open RTSP stream
```
**Giải pháp**:
- Kiểm tra RTSP URL đúng định dạng
- Đảm bảo camera RTSP có thể truy cập được

## 📝 Ghi chú

- Hệ thống sử dụng FaceNet để tạo face encoding 128 chiều
- Ngưỡng nhận diện mặc định: 0.6 (có thể điều chỉnh trong code)
- Hình ảnh đăng ký được lưu trong thư mục `uploads/`
- Session timeout: theo cấu hình Flask mặc định

## 🔒 Bảo mật

- Mật khẩu được hash bằng bcrypt
- Session-based authentication
- CORS được cấu hình cho development
- **Lưu ý**: Thay đổi `SECRET_KEY` trong production

## 📞 Hỗ trợ

Nếu gặp vấn đề, vui lòng:
1. Kiểm tra MongoDB đang chạy
2. Kiểm tra Python dependencies đã cài đặt
3. Xem log trong terminal
4. Kiểm tra browser console (F12)

## 📄 License

MIT License - Tự do sử dụng và chỉnh sửa

---

**Phát triển bởi**: AI Assistant
**Phiên bản**: 1.0.0
**Ngày**: 2026-01-17

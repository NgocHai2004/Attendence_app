from fastapi import FastAPI, Request, Response, HTTPException, Depends, Form, File, UploadFile, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import os
import cv2
import numpy as np
import base64
from datetime import datetime, timedelta
import csv
import io
from pathlib import Path
import json
from typing import Optional, List
from pydantic import BaseModel

from services import db_service, face_service, rtsp_service, scheduler, telegram_service, captcha_service

app = FastAPI(title="Face Recognition Attendance System")

# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv('SECRET_KEY', 'your-secret-key-change-this')
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Create upload directory
UPLOAD_FOLDER = Path('uploads')
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Pydantic models for request bodies
class RegisterUserRequest(BaseModel):
    username: str
    email: str
    password: str
    captcha_id: str = ''
    captcha_text: str = ''

class LoginRequest(BaseModel):
    email: str
    password: str
    captcha_id: str = ''
    captcha_text: str = ''

class RegisterFaceCameraRequest(BaseModel):
    name: str
    msv: str
    image: str
    class_name: str

class CreateClassRequest(BaseModel):
    class_name: str

class RenameClassRequest(BaseModel):
    old_name: str
    new_name: str

class DeleteSessionsRequest(BaseModel):
    session_ids: List[str]

class UpdateStudentRequest(BaseModel):
    id: str
    name: str
    msv: str
    image: Optional[str] = None

class UpdateStudentNameRequest(BaseModel):
    name: str

class StartRTSPRequest(BaseModel):
    rtsp_url: str
    class_name: Optional[str] = None
    attendance_type: str = 'in'

class BrowserSessionStopRequest(BaseModel):
    class_name: Optional[str] = None
    attendance_type: str = 'in'

class RecognizeFrameRequest(BaseModel):
    image: str
    class_name: Optional[str] = None
    attendance_type: str = 'in'

class CreateScheduleRequest(BaseModel):
    class_name: str
    attendance_type: str = 'in'
    rtsp_url: str = '0'
    start_hour: int
    start_minute: int = 0
    end_hour: int = 0
    end_minute: int = 0
    duration_minutes: int = 15
    selected_dates: List[str] = []
    send_telegram: bool = False

# Pydantic models for user management
class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = 'user'

class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UpdateUserPasswordRequest(BaseModel):
    password: str

# Pydantic models for Telegram
class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: str

class TelegramToggleRequest(BaseModel):
    send_on_stop: bool

# Helper function to get session
def get_session(request: Request):
    return request.session

def require_auth(request: Request):
    if 'user_id' not in request.session:
        raise HTTPException(status_code=401, detail='Not authenticated')
    return request.session

def require_admin(request: Request):
    """Require admin role for access"""
    if 'user_id' not in request.session:
        raise HTTPException(status_code=401, detail='Not authenticated')
    
    user = db_service.get_user_by_id(request.session['user_id'])
    if not user or user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')
    return request.session

# Page Routes
@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    """Redirect to login page"""
    if 'user_id' in request.session:
        return templates.TemplateResponse('dashboard.html', {'request': request})
    return templates.TemplateResponse('login.html', {'request': request})

@app.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse('login.html', {'request': request})

@app.get('/register', response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page"""
    return templates.TemplateResponse('register.html', {'request': request})

@app.get('/attendance-session/{session_id}', response_class=HTMLResponse)
async def attendance_session_page(request: Request, session_id: str):
    if 'user_id' not in request.session:
        return templates.TemplateResponse('login.html', {'request': request})
    return templates.TemplateResponse('attendance_detail.html', {
        'request': request,
        'session_id': session_id,
        'username': request.session.get('username', 'User')
    })

@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard page"""
    if 'user_id' not in request.session:
        return templates.TemplateResponse('login.html', {'request': request})
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'username': request.session.get('username', 'User')
    })

@app.get('/register-face', response_class=HTMLResponse)
async def register_face_page(request: Request):
    """Face registration page"""
    if 'user_id' not in request.session:
        return templates.TemplateResponse('login.html', {'request': request})
    return templates.TemplateResponse('register_face.html', {
        'request': request,
        'username': request.session.get('username', 'User')
    })

@app.get('/recognition', response_class=HTMLResponse)
async def recognition_page(request: Request):
    """RTSP recognition page"""
    if 'user_id' not in request.session:
        return templates.TemplateResponse('login.html', {'request': request})
    return templates.TemplateResponse('recognition.html', {
        'request': request,
        'username': request.session.get('username', 'User')
    })

@app.get('/edit-student', response_class=HTMLResponse)
async def edit_student_page(request: Request):
    """Edit student page"""
    if 'user_id' not in request.session:
        return templates.TemplateResponse('login.html', {'request': request})
    return templates.TemplateResponse('edit_student.html', {'request': request})

@app.get('/user-management', response_class=HTMLResponse)
async def user_management_page(request: Request):
    """User management page (Admin only)"""
    if 'user_id' not in request.session:
        return templates.TemplateResponse('login.html', {'request': request})
    
    # Check if user is admin
    user = db_service.get_user_by_id(request.session['user_id'])
    if not user or user.get('role') != 'admin':
        return templates.TemplateResponse('dashboard.html', {
            'request': request,
            'username': request.session.get('username', 'User'),
            'error': 'Bạn không có quyền truy cập trang này'
        })
    
    return templates.TemplateResponse('user_management.html', {
        'request': request,
        'username': request.session.get('username', 'User'),
        'role': user.get('role', 'user')
    })

# ============================================================
# CAPTCHA API Routes
# ============================================================

@app.get('/api/captcha/generate')
async def api_generate_captcha():
    """
    Tạo CAPTCHA mới.
    
    GIẢI THÍCH:
    - Client gọi API này để lấy hình ảnh CAPTCHA
    - Server trả về captcha_id (để xác thực sau) và captcha_image (base64)
    - Mã CAPTCHA thật KHÔNG được gửi cho client
    """
    try:
        result = captcha_service.create_captcha()
        return {
            'success': True,
            'captcha_id': result['captcha_id'],
            'captcha_image': result['captcha_image']
        }
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


# API Routes
@app.post('/api/register')
async def api_register(data: RegisterUserRequest):
    """Register a new user"""
    try:
        # ====== XÁC THỰC CAPTCHA TRƯỚC ======
        # Kiểm tra CAPTCHA trước khi xử lý đăng ký
        captcha_result = captcha_service.verify_captcha(data.captcha_id, data.captcha_text)
        if not captcha_result['valid']:
            return JSONResponse({
                'success': False,
                'message': captcha_result['message'],
                'captcha_error': True  # Flag để frontend biết cần refresh CAPTCHA
            }, status_code=400)
        
        username = data.username
        email = data.email
        password = data.password
        
        if not all([username, email, password]):
            return JSONResponse({'success': False, 'message': 'Missing required fields'}, status_code=400)
        
        # Check if user exists
        if db_service.get_user_by_email(email):
            return JSONResponse({'success': False, 'message': 'Email already registered'}, status_code=400)
        
        if db_service.get_user_by_username(username):
            return JSONResponse({'success': False, 'message': 'Username already taken'}, status_code=400)
        
        # Create user
        user_id = db_service.create_user(username, email, password)
        
        if user_id:
            return {'success': True, 'message': 'User registered successfully', 'user_id': user_id}
        else:
            return JSONResponse({'success': False, 'message': 'Failed to create user'}, status_code=500)
            
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/login')
async def api_login(request: Request, data: LoginRequest):
    """Login user"""
    try:
        # ====== XÁC THỰC CAPTCHA TRƯỚC ======
        # Kiểm tra CAPTCHA trước khi xử lý đăng nhập
        captcha_result = captcha_service.verify_captcha(data.captcha_id, data.captcha_text)
        if not captcha_result['valid']:
            return JSONResponse({
                'success': False,
                'message': captcha_result['message'],
                'captcha_error': True  # Flag để frontend biết cần refresh CAPTCHA
            }, status_code=400)
        
        email = data.email
        password = data.password
        
        if not all([email, password]):
            return JSONResponse({'success': False, 'message': 'Missing email or password'}, status_code=400)
        
        # Get user
        user = db_service.get_user_by_email(email)
        
        if not user:
            return JSONResponse({'success': False, 'message': 'Invalid email or password'}, status_code=401)
        
        # Check if user is active
        if not user.get('is_active', True):
            return JSONResponse({'success': False, 'message': 'Tài khoản đã bị vô hiệu hóa'}, status_code=401)
        
        # Verify password
        if not db_service.verify_password(password, user['password']):
            return JSONResponse({'success': False, 'message': 'Invalid email or password'}, status_code=401)
        
        # Set session
        request.session['user_id'] = str(user['_id'])
        request.session['username'] = user['username']
        request.session['role'] = user.get('role', 'user')
        
        return {
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': str(user['_id']),
                'username': user['username'],
                'email': user['email'],
                'role': user.get('role', 'user')
            }
        }
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/logout')
async def api_logout(request: Request):
    """Logout user"""
    request.session.clear()
    return {'success': True, 'message': 'Logged out successfully'}

@app.post('/api/register-face-camera')
async def api_register_face_camera(request: Request, data: RegisterFaceCameraRequest):
    """Register face from camera capture"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        name = data.name
        msv = data.msv
        image_data = data.image
        class_name = data.class_name
        print("DEBUG class_name:", class_name)
        
        if not all([name, msv, image_data]):
            return JSONResponse({'success': False, 'message': 'Thiếu tên, MSV hoặc ảnh'}, status_code=400)
        
        if not class_name:
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)

        if db_service.get_face_by_msv(msv, class_name):
            return JSONResponse({'success': False, 'message': 'MSV đã tồn tại trong lớp này'}, status_code=400)
        
        if ',' not in image_data:
            return JSONResponse({'success': False, 'message': 'Invalid image format'}, status_code=400)
        
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return JSONResponse({'success': False, 'message': 'Failed to decode image'}, status_code=400)
        
        # Detect face
        faces = face_service.detect_faces(image)
        
        if len(faces) == 0:
            return JSONResponse({'success': False, 'message': 'No face detected in image'}, status_code=400)
        
        if len(faces) > 1:
            return JSONResponse({'success': False, 'message': 'Multiple faces detected. Please ensure only one face is visible'}, status_code=400)
        
        face_box = faces[0]
        encoding = face_service.extract_face_encoding(image, face_box)
        
        if encoding is None:
            return JSONResponse({'success': False, 'message': 'Failed to extract face encoding'}, status_code=500)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_filename = f"{msv}_{timestamp}.jpg"
        image_path = UPLOAD_FOLDER / image_filename
        cv2.imwrite(str(image_path), image)
        
        face_id = db_service.create_face(name, msv, encoding, str(image_path), request.session['user_id'], class_name)
        
        if face_id:
            return {'success': True, 'message': f'Đăng ký thành công: {name} (MSV: {msv})'}
        else:
            return JSONResponse({'success': False, 'message': 'Failed to save face data'}, status_code=500)
            
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/register-face-upload')
async def api_register_face_upload(
    request: Request,
    name: str = Form(...),
    msv: str = Form(...),
    class_name: str = Form(...),
    image: UploadFile = File(...)
):
    """Register face from uploaded image"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        if not name:
            return JSONResponse({'success': False, 'message': 'Vui lòng nhập tên'}, status_code=400)

        if not msv:
            return JSONResponse({'success': False, 'message': 'Vui lòng nhập MSV'}, status_code=400)
        
        if class_name == '':
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)

        if db_service.get_face_by_msv(msv, class_name):
            return JSONResponse({'success': False, 'message': 'MSV đã tồn tại trong lớp này'}, status_code=400)
        
        file_bytes = np.frombuffer(await image.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if img is None:
            return JSONResponse({'success': False, 'message': 'Failed to decode image'}, status_code=400)
        
        # Detect face
        faces = face_service.detect_faces(img)
        
        if len(faces) == 0:
            return JSONResponse({'success': False, 'message': 'No face detected in image'}, status_code=400)
        
        if len(faces) > 1:
            return JSONResponse({'success': False, 'message': 'Multiple faces detected. Please upload image with only one face'}, status_code=400)
        
        face_box = faces[0]
        encoding = face_service.extract_face_encoding(img, face_box)
        
        if encoding is None:
            return JSONResponse({'success': False, 'message': 'Failed to extract face encoding'}, status_code=500)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_filename = f"{msv}_{timestamp}.jpg"
        image_path = UPLOAD_FOLDER / image_filename
        cv2.imwrite(str(image_path), img)
        
        face_id = db_service.create_face(name, msv, encoding, str(image_path), request.session['user_id'], class_name)
        
        if face_id:
            return {'success': True, 'message': f'Đăng ký thành công: {name} (MSV: {msv})'}
        else:
            return JSONResponse({'success': False, 'message': 'Failed to save face data'}, status_code=500)
            
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/classes')
async def api_get_classes(request: Request):
    """Get all classes"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        classes = db_service.get_all_classes()
        return {'success': True, 'classes': classes}
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/classes-stats')
async def api_get_classes_stats(request: Request):
    """Get all classes with statistics (student count, session count)"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        classes = db_service.get_all_classes()
        classes_stats = []
        
        for class_name in classes:
            # Get student count
            students = db_service.get_faces_by_class(class_name)
            student_count = len(students) if students else 0
            
            # Get session count
            sessions = db_service.get_attendance_sessions_by_class(class_name)
            session_count = len(sessions) if sessions else 0
            
            classes_stats.append({
                'name': class_name,
                'student_count': student_count,
                'session_count': session_count
            })
        
        return {'success': True, 'classes': classes_stats}
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.delete('/api/classes/{class_name}')
async def api_delete_class(request: Request, class_name: str):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        if not class_name:
            return JSONResponse({'success': False, 'message': 'Thiếu tên lớp'}, status_code=400)

        result = db_service.delete_class(class_name)
        if result is None:
            return JSONResponse({'success': False, 'message': 'Xóa lớp thất bại'}, status_code=500)

        return {'success': True, 'deleted': result}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/classes')
async def api_create_class(request: Request, data: CreateClassRequest):
    """Create a new empty class"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        class_name = data.class_name

        if not class_name or class_name.strip() == '':
            return JSONResponse({'success': False, 'message': 'Tên lớp không được để trống'}, status_code=400)

        class_name = class_name.strip()

        # Check if class already exists
        existing_classes = db_service.get_all_classes()
        if class_name in existing_classes:
            return JSONResponse({'success': False, 'message': 'Lớp này đã tồn tại'}, status_code=400)

        # Create the class
        result = db_service.create_class(class_name, request.session['user_id'])
        if result:
            return {'success': True, 'message': 'Thêm lớp thành công', 'class_name': class_name}
        else:
            return JSONResponse({'success': False, 'message': 'Thêm lớp thất bại'}, status_code=500)

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.put('/api/classes/rename')
async def api_rename_class(request: Request, data: RenameClassRequest):
    """Rename a class"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        old_name = data.old_name
        new_name = data.new_name

        if not old_name or not new_name:
            return JSONResponse({'success': False, 'message': 'Thiếu tên lớp cũ hoặc mới'}, status_code=400)

        new_name = new_name.strip()

        # Check if new name already exists
        existing_classes = db_service.get_all_classes()
        if new_name in existing_classes and new_name != old_name:
            return JSONResponse({'success': False, 'message': 'Tên lớp mới đã tồn tại'}, status_code=400)

        # Rename the class
        result = db_service.rename_class(old_name, new_name)
        if result:
            return {'success': True, 'message': 'Đổi tên lớp thành công', 'result': result}
        else:
            return JSONResponse({'success': False, 'message': 'Đổi tên lớp thất bại'}, status_code=500)

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/attendance')
async def api_get_attendance(request: Request, class_name: str = Query(None)):
    """Get attendance records by class"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        if not class_name:
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)
        
        attendance = db_service.get_attendance_by_class(class_name)
        return {'success': True, 'attendance': attendance}
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

# Global variables for browser session
browser_recognized_faces = {}
browser_session_start = None

def get_browser_session_summary(class_name):
    global browser_recognized_faces
    students = db_service.get_faces_by_class(class_name)
    student_msvs = {f.get('msv') for f in students if f.get('msv')}
    
    present_msvs = set()
    for face_data in browser_recognized_faces.values():
        msv = face_data.get('msv')
        if msv:
            present_msvs.add(msv)
    
    present = len(present_msvs & student_msvs)
    total = len(student_msvs)
    absent = total - present
    if absent < 0:
        absent = 0
    return {'present': present, 'absent': absent, 'total': total}

@app.get('/api/attendance-summary')
async def api_get_attendance_summary(
    request: Request,
    class_name: str = Query(None),
    attendance_type: str = Query(None),
    session_param: str = Query(None, alias='session')
):
    """Get attendance summary by class"""
    global browser_recognized_faces, browser_session_start
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        if not class_name:
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)
        
        use_session = session_param == '1'
        
        if use_session and browser_session_start:
            summary = get_browser_session_summary(class_name)
        elif use_session and rtsp_service.is_running and rtsp_service.session_start_time:
            if class_name == rtsp_service.class_name and attendance_type == rtsp_service.attendance_type:
                summary = rtsp_service.get_session_summary()
            else:
                summary = db_service.get_attendance_summary(class_name, attendance_type)
        else:
            summary = db_service.get_attendance_summary(class_name, attendance_type)
        return {'success': True, 'summary': summary}
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/attendance-sessions')
async def api_get_attendance_sessions(
    request: Request,
    class_name: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None)
):
    """Get attendance sessions by class with optional date filter"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        if not class_name:
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)
        
        # Parse dates if provided
        start_datetime = None
        end_datetime = None
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date:
            try:
                # Add 1 day to include the end date fully
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            except ValueError:
                pass
        
        sessions = db_service.get_attendance_sessions_by_class(class_name, start_date=start_datetime, end_date=end_datetime)
        return {'success': True, 'sessions': sessions}
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.delete('/api/attendance-sessions')
async def api_delete_attendance_sessions(request: Request, data: DeleteSessionsRequest):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        session_ids = data.session_ids

        if not session_ids:
            return JSONResponse({'success': False, 'message': 'Session ids are required'}, status_code=400)

        deleted_count = db_service.delete_attendance_sessions(session_ids)
        return {'success': True, 'deleted': deleted_count}

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.delete('/api/attendance-sessions/{session_id}')
async def api_delete_attendance_session(request: Request, session_id: str):
    """Delete a single attendance session by ID"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        if not session_id:
            return JSONResponse({'success': False, 'message': 'Session id is required'}, status_code=400)

        deleted_count = db_service.delete_attendance_sessions([session_id])
        if deleted_count > 0:
            return {'success': True, 'deleted': deleted_count}
        else:
            return JSONResponse({'success': False, 'message': 'Session not found'}, status_code=404)

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/attendance-sessions/export')
async def api_export_attendance_sessions(request: Request, data: DeleteSessionsRequest):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        session_ids = data.session_ids

        if not session_ids:
            return JSONResponse({'success': False, 'message': 'Session ids are required'}, status_code=400)

        rows = []
        for session_id in session_ids:
            record = db_service.get_attendance_session_by_id(session_id)
            if record:
                rows.append(record)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['class_name', 'attendance_type', 'start_time', 'end_time', 'present', 'absent', 'total'])
        for row in rows:
            writer.writerow([
                row.get('class_name', ''),
                row.get('attendance_type', ''),
                row.get('start_time', ''),
                row.get('end_time', ''),
                row.get('present', 0),
                row.get('absent', 0),
                row.get('total', 0)
            ])

        output.seek(0)
        filename = f"attendance_sessions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=output.getvalue(),
            media_type='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/export-session/{session_id}')
async def api_export_single_session(request: Request, session_id: str):
    """Export a single attendance session to CSV"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        if not session_id:
            return JSONResponse({'success': False, 'message': 'Session id is required'}, status_code=400)

        session_record = db_service.get_attendance_session_by_id(session_id)
        if not session_record:
            return JSONResponse({'success': False, 'message': 'Session not found'}, status_code=404)

        class_name = session_record.get('class_name')
        attendance_type = session_record.get('attendance_type')
        start_time = session_record.get('start_time')
        end_time = session_record.get('end_time')
        present_faces = session_record.get('present_faces', [])

        # Format times for display
        start_time_str = start_time.strftime('%d/%m/%Y %H:%M:%S') if start_time else ''
        end_time_str = end_time.strftime('%d/%m/%Y %H:%M:%S') if end_time else ''
        attendance_type_str = 'Điểm danh VÀO' if attendance_type == 'in' else 'Điểm danh RA'

        # Get all students in class
        all_faces = db_service.get_faces_by_class(class_name)
        all_students = {f.get('msv'): f.get('name') for f in all_faces if f.get('msv')}

        # Build present list from session's present_faces (more reliable)
        present_data = {}
        for face in present_faces:
            msv = face.get('msv')
            if msv:
                present_data[msv] = face.get('timestamp', '')
        
        # If present_faces is empty, fall back to attendance records
        if not present_data:
            records = db_service.get_attendance_records_in_range(
                class_name, attendance_type, start_time, end_time
            )
            for record in records:
                msv = record.get('msv')
                if msv:
                    present_data[msv] = record.get('timestamp', '')

        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write session info header
        writer.writerow(['THÔNG TIN PHIÊN ĐIỂM DANH'])
        writer.writerow(['Lớp', class_name])
        writer.writerow(['Loại điểm danh', attendance_type_str])
        writer.writerow(['Thời gian bắt đầu', start_time_str])
        writer.writerow(['Thời gian kết thúc', end_time_str])
        writer.writerow(['Tổng sinh viên', len(all_students)])
        writer.writerow(['Có mặt', len(present_data)])
        writer.writerow(['Vắng', len(all_students) - len(present_data)])
        writer.writerow([])  # Empty row as separator
        
        # Write student list header
        writer.writerow(['STT', 'MSV', 'Họ và tên', 'Trạng thái'])

        stt = 1
        for msv, name in all_students.items():
            status = 'Có mặt' if msv in present_data else 'Vắng'
            writer.writerow([stt, msv, name, status])
            stt += 1

        output.seek(0)
        filename = f"attendance_{class_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=output.getvalue(),
            media_type='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/attendance-session-detail')
async def api_get_attendance_session_detail(request: Request, session_id: str = Query(None)):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        if not session_id:
            return JSONResponse({'success': False, 'message': 'Session id is required'}, status_code=400)

        session_record = db_service.get_attendance_session_by_id(session_id)
        if not session_record:
            return JSONResponse({'success': False, 'message': 'Session not found'}, status_code=404)

        class_name = session_record.get('class_name')
        attendance_type = session_record.get('attendance_type')
        start_time = session_record.get('start_time')
        end_time = session_record.get('end_time')

        records = db_service.get_attendance_records_in_range(
            class_name,
            attendance_type,
            start_time,
            end_time
        )
        # Use MSV as unique identifier instead of name
        present_map = {}
        for record in records:
            msv = record.get('msv') or ''
            if not msv:
                continue
            existing = present_map.get(msv)
            if existing is None or record.get('timestamp') > existing.get('timestamp'):
                present_map[msv] = record

        all_faces = db_service.get_faces_by_class(class_name)
        
        # Build face info map using MSV as key (includes db_image for both present and absent)
        face_info_map = {}
        for face in all_faces:
            msv = face.get('msv')
            if msv:
                # Read image and convert to base64
                image_path = face.get('image_path')
                db_image_b64 = None
                if image_path and os.path.exists(image_path):
                    try:
                        img = cv2.imread(image_path)
                        if img is not None:
                            _, buffer = cv2.imencode('.jpg', img)
                            db_image_b64 = base64.b64encode(buffer).decode('utf-8')
                    except:
                        pass
                face_info_map[msv] = {
                    'name': face.get('name', ''),
                    'msv': msv,
                    'db_image': db_image_b64
                }
        
        present_faces = []
        if present_map:
            for msv, record in present_map.items():
                face_info = face_info_map.get(msv, {})
                present_faces.append({
                    'name': record.get('name') or face_info.get('name', ''),
                    'msv': msv,
                    'face_image': record.get('face_image'),
                    'db_image': face_info.get('db_image')
                })
        elif session_record.get('present_faces'):
            pf = session_record.get('present_faces', [])
            for face in pf:
                msv = face.get('msv')
                if msv:
                    face_info = face_info_map.get(msv, {})
                    present_faces.append({
                        'name': face.get('name') or face_info.get('name', ''),
                        'msv': msv,
                        'face_image': face.get('face_image'),
                        'db_image': face_info.get('db_image')
                    })

        # Get all student MSVs in the class
        all_student_msvs = set(db_service.get_class_students_msvs(class_name))
        present_msvs = {face.get('msv') for face in present_faces if face.get('msv')}
        
        absent_names = []
        absent_faces = []
        for msv in all_student_msvs:
            if msv not in present_msvs:
                # Get face info for absent student
                face_info = face_info_map.get(msv, {'name': '', 'msv': msv, 'db_image': None})
                absent_names.append(face_info.get('name', ''))
                absent_faces.append({
                    'name': face_info.get('name', ''),
                    'msv': msv,
                    'face_image': face_info.get('db_image')  # Use db_image as face_image for absent
                })

        total_students = len(all_student_msvs)
        present_count = len(present_faces)
        absent_count = len(absent_faces)

        return {
            'success': True,
            'session': {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'start_time': start_time.isoformat() if hasattr(start_time, 'isoformat') else start_time,
                'end_time': end_time.isoformat() if hasattr(end_time, 'isoformat') else end_time,
                'present': present_count,
                'absent': absent_count,
                'total': total_students
            },
            'present_names': [face.get('name') for face in present_faces],
            'present_faces': present_faces,
            'absent_names': absent_names,
            'absent_faces': absent_faces
        }

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/class-students')
async def api_get_class_students(request: Request, class_name: str = Query(None)):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        if not class_name:
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)

        students = db_service.get_faces_by_class(class_name)
        return {'success': True, 'students': students}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/all-students')
async def api_get_all_students(
    request: Request,
    search: str = Query(None),
    sort_by: str = Query('name')
):
    """Get all students from all classes with search and sort"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        students = db_service.get_all_students(search_msv=search, sort_by=sort_by)
        return {'success': True, 'students': students, 'total': len(students)}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/student/{student_id}')
async def api_get_student(request: Request, student_id: str):
    """Get single student by ID"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        student = db_service.get_face_by_id(student_id)
        if not student:
            return JSONResponse({'success': False, 'message': 'Student not found'}, status_code=404)

        return {
            'success': True,
            'student': {
                'id': str(student['_id']),
                'name': student.get('name'),
                'msv': student.get('msv'),
                'class_name': student.get('class_name'),
                'image_path': student.get('image_path'),
                'created_at': student.get('created_at').isoformat() if student.get('created_at') else None
            }
        }
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/student-image/{student_id}')
async def api_get_student_image(student_id: str):
    """Get student face image"""
    try:
        student = db_service.get_face_by_id(student_id)
        if not student or not student.get('image_path'):
            return JSONResponse({'success': False, 'message': 'Image not found'}, status_code=404)

        image_path = student['image_path']
        if not os.path.isabs(image_path):
            image_path = os.path.join(os.getcwd(), image_path)

        if not os.path.exists(image_path):
            return JSONResponse({'success': False, 'message': 'Image file not found'}, status_code=404)

        return FileResponse(image_path, media_type='image/jpeg')
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/student/update')
async def api_update_student(request: Request, data: UpdateStudentRequest):
    """Update student info (name, msv, image)"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        student_id = data.id
        name = data.name
        msv = data.msv
        image_data = data.image

        if not student_id:
            return JSONResponse({'success': False, 'message': 'Student ID is required'}, status_code=400)

        if not name or not msv:
            return JSONResponse({'success': False, 'message': 'Name and MSV are required'}, status_code=400)

        # Get current student info
        student = db_service.get_face_by_id(student_id)
        if not student:
            return JSONResponse({'success': False, 'message': 'Student not found'}, status_code=404)

        # Check if MSV already exists (for different student in same class)
        existing = db_service.get_face_by_msv(msv, student.get('class_name'))
        if existing and str(existing['_id']) != student_id:
            return JSONResponse({'success': False, 'message': 'MSV đã tồn tại trong lớp này'}, status_code=400)

        # Process new image if provided
        new_image_path = None
        new_encoding = None
        if image_data and ',' in image_data:
            image_bytes = base64.b64decode(image_data.split(',')[1])
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is not None:
                # Detect and extract face encoding
                faces = face_service.detect_faces(image)
                if len(faces) == 0:
                    return JSONResponse({'success': False, 'message': 'Không phát hiện khuôn mặt trong ảnh'}, status_code=400)
                if len(faces) > 1:
                    return JSONResponse({'success': False, 'message': 'Phát hiện nhiều khuôn mặt. Vui lòng chọn ảnh có 1 khuôn mặt'}, status_code=400)

                face_box = faces[0]
                new_encoding = face_service.extract_face_encoding(image, face_box)

                # Save new image
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                image_filename = f"{msv}_{timestamp}.jpg"
                new_image_path = str(UPLOAD_FOLDER / image_filename)
                cv2.imwrite(new_image_path, image)

        # Update student in database
        updated = db_service.update_face(student_id, name, msv, new_encoding, new_image_path)
        if updated:
            return {'success': True, 'message': 'Cập nhật thành công'}
        return JSONResponse({'success': False, 'message': 'Cập nhật thất bại'}, status_code=400)

    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.put('/api/class-students/{student_id}')
async def api_update_class_student(request: Request, student_id: str, data: UpdateStudentNameRequest):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        name = data.name
        if not name:
            return JSONResponse({'success': False, 'message': 'Name is required'}, status_code=400)

        updated = db_service.update_face_name(student_id, name)
        if updated:
            return {'success': True}
        return JSONResponse({'success': False, 'message': 'Update failed'}, status_code=400)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.delete('/api/class-students/{student_id}')
async def api_delete_class_student(request: Request, student_id: str):
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        deleted = db_service.delete_face(student_id)
        if deleted:
            return {'success': True}
        return JSONResponse({'success': False, 'message': 'Delete failed'}, status_code=400)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/faces')
async def api_get_faces(request: Request):
    """Get all registered faces"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        faces = db_service.get_all_faces()
        
        face_list = []
        for face in faces:
            face_list.append({
                'id': str(face['_id']),
                'name': face['name'],
                'msv': face.get('msv'),
                'class_name': face.get('class_name'),
                'created_at': face['created_at'].isoformat() if face.get('created_at') else None
            })
        
        return {'success': True, 'faces': face_list}
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/start-rtsp')
async def api_start_rtsp(request: Request, data: StartRTSPRequest):
    """Start RTSP stream"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        rtsp_url = data.rtsp_url
        class_name = data.class_name
        attendance_type = data.attendance_type
        
        if not rtsp_url:
            return JSONResponse({'success': False, 'message': 'RTSP URL is required'}, status_code=400)
        
        success = rtsp_service.start_stream(rtsp_url, class_name, request.session['user_id'], attendance_type)
        
        if success:
            return {'success': True, 'message': 'RTSP stream started'}
        else:
            return JSONResponse({'success': False, 'message': 'Failed to start RTSP stream'}, status_code=500)
            
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/stop-rtsp')
async def api_stop_rtsp():
    """Stop RTSP stream"""
    try:
        rtsp_service.stop_stream()
        return {'success': True, 'message': 'RTSP stream stopped'}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/video-feed')
async def video_feed():
    """Video feed endpoint"""
    def generate():
        while rtsp_service.is_running:
            frame = rtsp_service.get_current_frame()
            if frame is not None:
                _, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')

@app.get('/api/recognized-faces')
async def api_recognized_faces():
    """Get currently recognized faces"""
    try:
        faces = rtsp_service.get_recognized_faces()
        return {'success': True, 'faces': faces}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/browser-session/start')
async def api_browser_session_start():
    """Start browser camera session"""
    global browser_recognized_faces, browser_session_start
    browser_recognized_faces = {}
    browser_session_start = datetime.now()
    return {'success': True}

@app.post('/api/browser-session/stop')
async def api_browser_session_stop(request: Request, data: BrowserSessionStopRequest):
    """Stop browser camera session and save attendance"""
    global browser_recognized_faces, browser_session_start
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        class_name = data.class_name
        attendance_type = data.attendance_type

        if class_name and browser_session_start:
            end_time = datetime.now()
            present_faces = []
            for face_data in browser_recognized_faces.values():
                present_faces.append({
                    'name': face_data.get('name'),
                    'msv': face_data.get('msv'),
                    'face_image': face_data.get('face_image')
                })

            print(f"DEBUG browser_session_stop: class={class_name}, type={attendance_type}")
            print(f"DEBUG browser_session_stop: start={browser_session_start}, end={end_time}")
            print(f"DEBUG browser_session_stop: present_faces count={len(present_faces)}")
            print(f"DEBUG browser_session_stop: browser_recognized_faces={browser_recognized_faces}")

            summary = db_service.get_attendance_summary_in_range(
                class_name, attendance_type, browser_session_start, end_time
            )
            print(f"DEBUG browser_session_stop: summary={summary}")
            
            db_service.create_attendance_session(
                class_name, attendance_type, request.session['user_id'],
                browser_session_start, end_time,
                summary.get('present', 0), summary.get('total', 0),
                summary.get('absent', 0), present_faces=present_faces
            )

            # Send Telegram notification if enabled
            if telegram_service.send_on_stop and telegram_service.is_configured():
                telegram_service.send_attendance_summary_async(
                    class_name=class_name,
                    attendance_type=attendance_type,
                    present=summary.get('present', 0),
                    absent=summary.get('absent', 0),
                    total=summary.get('total', 0),
                    start_time=browser_session_start,
                    end_time=end_time,
                    present_faces=present_faces,
                    is_scheduled=False
                )

        browser_recognized_faces = {}
        browser_session_start = None
        return {'success': True}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/recognize-frame')
async def api_recognize_frame(request: Request, data: RecognizeFrameRequest):
    """Recognize faces from browser camera frame"""
    global browser_recognized_faces
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        image_data = data.image
        class_name = data.class_name
        attendance_type = data.attendance_type

        if not image_data or ',' not in image_data:
            return JSONResponse({'success': False, 'message': 'Invalid image'}, status_code=400)

        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return JSONResponse({'success': False, 'message': 'Failed to decode image'}, status_code=400)

        faces = face_service.detect_faces(frame)
        if not faces:
            return {'success': True, 'faces': list(browser_recognized_faces.values())}

        known_faces = db_service.get_faces_by_class(class_name) if class_name else []
        new_recognitions = []

        for face_box in faces:
            encoding = face_service.extract_face_encoding(frame, face_box)
            if encoding is None:
                continue

            match, confidence = face_service.identify_face(encoding, known_faces)
            name = match.get('name') if match else None
            msv = match.get('msv') if match else None

            if match and confidence < 70.0:
                continue

            x, y, w, h = face_box
            face_crop = frame[y:y+h, x:x+w]
            face_image_base64 = None
            if face_crop.size > 0:
                _, buffer = cv2.imencode('.jpg', face_crop)
                face_image_base64 = base64.b64encode(buffer).decode('utf-8')

            db_image_base64 = None
            if match and match.get('image_path'):
                img_path = match['image_path']
                if not os.path.isabs(img_path):
                    img_path = os.path.join(os.getcwd(), img_path)
                if os.path.exists(img_path):
                    db_img = cv2.imread(img_path)
                    if db_img is not None:
                        _, db_buffer = cv2.imencode('.jpg', db_img)
                        db_image_base64 = base64.b64encode(db_buffer).decode('utf-8')

            if name:
                person_key = msv or name
                normalized_name = db_service._normalize_name(name)
                
                if person_key not in browser_recognized_faces:
                    db_service.create_attendance(
                        name, class_name, request.session['user_id'], attendance_type,
                        attendance_time=datetime.now(), allow_duplicate=True,
                        face_image=face_image_base64, msv=msv
                    )

                browser_recognized_faces[person_key] = {
                    'name': name,
                    'msv': msv,
                    'confidence': round(confidence, 2),
                    'class_name': class_name,
                    'attendance_type': attendance_type,
                    'box': {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)},
                    'face_image': face_image_base64,
                    'db_image': db_image_base64
                }

        return {'success': True, 'faces': list(browser_recognized_faces.values())}

    except Exception as e:
        print(f"Error in recognize-frame: {e}")
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

# Schedule API endpoints
@app.post('/api/schedules')
async def api_create_schedule(request: Request, data: CreateScheduleRequest):
    """Create a new attendance schedule"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        class_name = data.class_name
        attendance_type = data.attendance_type
        rtsp_url = data.rtsp_url
        start_hour = data.start_hour
        start_minute = data.start_minute
        end_hour = data.end_hour
        end_minute = data.end_minute
        duration_minutes = data.duration_minutes
        selected_dates = data.selected_dates
        send_telegram = data.send_telegram

        if not class_name:
            return JSONResponse({'success': False, 'message': 'Class name is required'}, status_code=400)
        if start_hour is None:
            return JSONResponse({'success': False, 'message': 'Start hour is required'}, status_code=400)
        if not selected_dates:
            return JSONResponse({'success': False, 'message': 'Please select at least one date'}, status_code=400)

        schedule_id = db_service.create_schedule(
            class_name, attendance_type, rtsp_url,
            int(start_hour), int(start_minute),
            int(duration_minutes),
            request.session['user_id'],
            send_telegram=send_telegram,
            end_hour=int(end_hour),
            end_minute=int(end_minute),
            selected_dates=selected_dates
        )

        if schedule_id:
            return {'success': True, 'schedule_id': schedule_id}
        return JSONResponse({'success': False, 'message': 'Failed to create schedule'}, status_code=500)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/schedules')
async def api_get_schedules(request: Request, class_name: str = Query(None)):
    """Get schedules for a class or all schedules"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        if class_name:
            schedules = db_service.get_schedules_by_class(class_name)
        else:
            # Return all schedules across all classes
            schedules = db_service.get_all_schedules()
        
        scheduler_status = scheduler.get_status()
        return {'success': True, 'schedules': schedules, 'scheduler': scheduler_status}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.put('/api/schedules/{schedule_id}/toggle')
async def api_toggle_schedule(request: Request, schedule_id: str):
    """Toggle schedule active status"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        result = db_service.toggle_schedule(schedule_id)
        if result is None:
            return JSONResponse({'success': False, 'message': 'Schedule not found'}, status_code=404)
        return {'success': True, 'active': result}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.delete('/api/schedules/{schedule_id}')
async def api_delete_schedule(request: Request, schedule_id: str):
    """Delete a schedule"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        deleted = db_service.delete_schedule(schedule_id)
        if deleted:
            return {'success': True}
        return JSONResponse({'success': False, 'message': 'Delete failed'}, status_code=400)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

# ==================== USER MANAGEMENT APIs (Admin only) ====================

@app.get('/api/users')
async def api_get_users(request: Request):
    """Get all users (Admin only)"""
    try:
        require_admin(request)
        users = db_service.get_all_users()
        return {'success': True, 'users': users}
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/users/{user_id}')
async def api_get_user(request: Request, user_id: str):
    """Get single user details (Admin only)"""
    try:
        require_admin(request)
        user = db_service.get_user_by_id(user_id)
        if not user:
            return JSONResponse({'success': False, 'message': 'User not found'}, status_code=404)
        
        return {
            'success': True,
            'user': {
                'id': str(user['_id']),
                'username': user.get('username', ''),
                'email': user.get('email', ''),
                'role': user.get('role', 'user'),
                'is_active': user.get('is_active', True),
                'created_at': user.get('created_at')
            }
        }
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/users')
async def api_create_user(request: Request, data: CreateUserRequest):
    """Create a new user (Admin only)"""
    try:
        require_admin(request)
        
        # Validate required fields
        if not all([data.username, data.email, data.password]):
            return JSONResponse({'success': False, 'message': 'Vui lòng điền đầy đủ thông tin'}, status_code=400)
        
        # Check if email exists
        if db_service.get_user_by_email(data.email):
            return JSONResponse({'success': False, 'message': 'Email đã tồn tại'}, status_code=400)
        
        # Check if username exists
        if db_service.get_user_by_username(data.username):
            return JSONResponse({'success': False, 'message': 'Tên đăng nhập đã tồn tại'}, status_code=400)
        
        # Validate role
        if data.role not in ['user', 'admin']:
            return JSONResponse({'success': False, 'message': 'Role không hợp lệ'}, status_code=400)
        
        # Create user
        user_id = db_service.create_user(data.username, data.email, data.password, data.role)
        
        if user_id:
            return {'success': True, 'message': 'Tạo tài khoản thành công', 'user_id': user_id}
        else:
            return JSONResponse({'success': False, 'message': 'Không thể tạo tài khoản'}, status_code=500)
            
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.put('/api/users/{user_id}')
async def api_update_user(request: Request, user_id: str, data: UpdateUserRequest):
    """Update user information (Admin only)"""
    try:
        require_admin(request)
        
        # Check if user exists
        user = db_service.get_user_by_id(user_id)
        if not user:
            return JSONResponse({'success': False, 'message': 'Không tìm thấy người dùng'}, status_code=404)
        
        # Prevent admin from deactivating themselves
        if user_id == request.session.get('user_id') and data.is_active == False:
            return JSONResponse({'success': False, 'message': 'Không thể vô hiệu hóa tài khoản của chính mình'}, status_code=400)
        
        # Prevent admin from removing their own admin role
        if user_id == request.session.get('user_id') and data.role == 'user':
            return JSONResponse({'success': False, 'message': 'Không thể thay đổi quyền của chính mình'}, status_code=400)
        
        # Check email uniqueness if changing email
        if data.email and data.email != user.get('email'):
            existing = db_service.get_user_by_email(data.email)
            if existing:
                return JSONResponse({'success': False, 'message': 'Email đã tồn tại'}, status_code=400)
        
        # Check username uniqueness if changing username
        if data.username and data.username != user.get('username'):
            existing = db_service.get_user_by_username(data.username)
            if existing:
                return JSONResponse({'success': False, 'message': 'Tên đăng nhập đã tồn tại'}, status_code=400)
        
        # Update user
        result = db_service.update_user(user_id, data.username, data.email, data.role, data.is_active)
        
        if result:
            return {'success': True, 'message': 'Cập nhật thành công'}
        else:
            return JSONResponse({'success': False, 'message': 'Không có thay đổi nào được thực hiện'}, status_code=400)
            
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.put('/api/users/{user_id}/password')
async def api_update_user_password(request: Request, user_id: str, data: UpdateUserPasswordRequest):
    """Update user password (Admin only)"""
    try:
        require_admin(request)
        
        # Check if user exists
        user = db_service.get_user_by_id(user_id)
        if not user:
            return JSONResponse({'success': False, 'message': 'Không tìm thấy người dùng'}, status_code=404)
        
        if not data.password or len(data.password) < 6:
            return JSONResponse({'success': False, 'message': 'Mật khẩu phải có ít nhất 6 ký tự'}, status_code=400)
        
        result = db_service.update_user_password(user_id, data.password)
        
        if result:
            return {'success': True, 'message': 'Đổi mật khẩu thành công'}
        else:
            return JSONResponse({'success': False, 'message': 'Không thể đổi mật khẩu'}, status_code=500)
            
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.delete('/api/users/{user_id}')
async def api_delete_user(request: Request, user_id: str):
    """Delete a user (Admin only)"""
    try:
        require_admin(request)
        
        # Prevent admin from deleting themselves
        if user_id == request.session.get('user_id'):
            return JSONResponse({'success': False, 'message': 'Không thể xóa tài khoản của chính mình'}, status_code=400)
        
        # Check if user exists
        user = db_service.get_user_by_id(user_id)
        if not user:
            return JSONResponse({'success': False, 'message': 'Không tìm thấy người dùng'}, status_code=404)
        
        result = db_service.delete_user(user_id)
        
        if result:
            return {'success': True, 'message': 'Xóa tài khoản thành công'}
        else:
            return JSONResponse({'success': False, 'message': 'Không thể xóa tài khoản'}, status_code=500)
            
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/users/stats/count')
async def api_get_user_stats(request: Request):
    """Get user statistics (Admin only)"""
    try:
        require_admin(request)
        
        total_users = db_service.count_users()
        admin_users = db_service.count_admin_users()
        
        return {
            'success': True,
            'stats': {
                'total_users': total_users,
                'admin_users': admin_users,
                'regular_users': total_users - admin_users
            }
        }
    except HTTPException as e:
        return JSONResponse({'success': False, 'message': e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.get('/api/me')
async def api_get_current_user(request: Request):
    """Get current logged in user info"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        
        user = db_service.get_user_by_id(request.session['user_id'])
        if not user:
            return JSONResponse({'success': False, 'message': 'User not found'}, status_code=404)
        
        return {
            'success': True,
            'user': {
                'id': str(user['_id']),
                'username': user.get('username', ''),
                'email': user.get('email', ''),
                'role': user.get('role', 'user'),
                'is_active': user.get('is_active', True)
            }
        }
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

# ==================== TELEGRAM APIs ====================

@app.get('/api/telegram/config')
async def api_get_telegram_config(request: Request):
    """Get current Telegram configuration"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)
        return {'success': True, 'config': telegram_service.get_config()}
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/telegram/config')
async def api_set_telegram_config(request: Request, data: TelegramConfigRequest):
    """Update Telegram bot configuration"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        enabled = telegram_service.configure(data.bot_token, data.chat_id)
        return {
            'success': True,
            'enabled': enabled,
            'message': 'Cấu hình Telegram đã được cập nhật' if enabled else 'Telegram đã bị tắt (thiếu token hoặc chat_id)'
        }
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/telegram/toggle')
async def api_toggle_telegram(request: Request, data: TelegramToggleRequest):
    """Toggle Telegram notification for current session"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        telegram_service.set_send_on_stop(data.send_on_stop)
        return {
            'success': True,
            'send_on_stop': telegram_service.send_on_stop,
            'message': 'Đã bật gửi Telegram' if data.send_on_stop else 'Đã tắt gửi Telegram'
        }
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@app.post('/api/telegram/test')
async def api_test_telegram(request: Request):
    """Test Telegram bot connection"""
    try:
        if 'user_id' not in request.session:
            return JSONResponse({'success': False, 'message': 'Not authenticated'}, status_code=401)

        result = telegram_service.test_connection()
        return result
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

# Startup event
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("Face Recognition Attendance System")
    print("="*50)
    print("\nStarting FastAPI application...")
    print("Access the application at: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Ensure at least one admin exists
    db_service.ensure_admin_exists()
    
    # Start the scheduler
    scheduler.start()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)

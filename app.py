from flask import Flask, request, jsonify, render_template, Response, session
from flask_cors import CORS
import os
import cv2
import numpy as np
import base64
from datetime import datetime
import csv
import io
from pathlib import Path
import json

from services import db_service, face_service, rtsp_service, scheduler

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
CORS(app)

# Create upload directory
UPLOAD_FOLDER = Path('uploads')
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Routes
@app.route('/')
def index():
    """Redirect to login page"""
    if 'user_id' in session:
        return render_template('dashboard.html')
    return render_template('login.html')

@app.route('/login')
def login_page():
    """Login page"""
    return render_template('login.html')

@app.route('/register')
def register_page():
    """Registration page"""
    return render_template('register.html')

@app.route('/attendance-session/<session_id>')
def attendance_session_page(session_id):
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('attendance_detail.html', session_id=session_id, username=session.get('username', 'User'))

@app.route('/dashboard')
def dashboard():
    """Dashboard page"""
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('dashboard.html', username=session.get('username', 'User'))

@app.route('/register-face')
def register_face_page():
    """Face registration page"""
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('register_face.html', username=session.get('username', 'User'))

@app.route('/recognition')
def recognition_page():
    """RTSP recognition page"""
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('recognition.html', username=session.get('username', 'User'))

# API Routes
@app.route('/api/register', methods=['POST'])
def api_register():
    """Register a new user"""
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not all([username, email, password]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Check if user exists
        if db_service.get_user_by_email(email):
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
        if db_service.get_user_by_username(username):
            return jsonify({'success': False, 'message': 'Username already taken'}), 400
        
        # Create user
        user_id = db_service.create_user(username, email, password)
        
        if user_id:
            return jsonify({'success': True, 'message': 'User registered successfully', 'user_id': user_id})
        else:
            return jsonify({'success': False, 'message': 'Failed to create user'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    """Login user"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not all([email, password]):
            return jsonify({'success': False, 'message': 'Missing email or password'}), 400
        
        # Get user
        user = db_service.get_user_by_email(email)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
        
        # Verify password
        if not db_service.verify_password(password, user['password']):
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
        
        # Set session
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        
        return jsonify({
            'success': True, 
            'message': 'Login successful',
            'user': {
                'id': str(user['_id']),
                'username': user['username'],
                'email': user['email']
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logout', methods=['GET'])
def api_logout():
    """Logout user"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/register-face-camera', methods=['POST'])
def api_register_face_camera():
    """Register face from camera capture"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        data = request.get_json()
        name = data.get('name')
        msv = data.get('msv')
        image_data = data.get('image')  # Base64 encoded image
        class_name = data.get('class_name')  # Class name
        print("DEBUG class_name:", class_name)
        
        if not all([name, msv, image_data]):
            return jsonify({'success': False, 'message': 'Thiếu tên, MSV hoặc ảnh'}), 400
        
        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400

        if db_service.get_face_by_msv(msv, class_name):
            return jsonify({'success': False, 'message': 'MSV đã tồn tại trong lớp này'}), 400
        
        if ',' not in image_data:
            return jsonify({'success': False, 'message': 'Invalid image format'}), 400
        
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'success': False, 'message': 'Failed to decode image'}), 400
        
        # Detect face
        faces = face_service.detect_faces(image)
        
        if len(faces) == 0:
            return jsonify({'success': False, 'message': 'No face detected in image'}), 400
        
        if len(faces) > 1:
            return jsonify({'success': False, 'message': 'Multiple faces detected. Please ensure only one face is visible'}), 400
        
        face_box = faces[0]
        encoding = face_service.extract_face_encoding(image, face_box)
        
        if encoding is None:
            return jsonify({'success': False, 'message': 'Failed to extract face encoding'}), 500
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_filename = f"{msv}_{timestamp}.jpg"
        image_path = UPLOAD_FOLDER / image_filename
        cv2.imwrite(str(image_path), image)
        
        face_id = db_service.create_face(name, msv, encoding, str(image_path), session['user_id'], class_name)
        
        if face_id:
            return jsonify({'success': True, 'message': f'Đăng ký thành công: {name} (MSV: {msv})'})
        else:
            return jsonify({'success': False, 'message': 'Failed to save face data'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/register-face-upload', methods=['POST'])
def api_register_face_upload():
    """Register face from uploaded image"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        name = request.form.get('name')
        msv = request.form.get('msv')
        class_name = request.form.get('class_name')
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image file provided'}), 400
        
        if not name:
            return jsonify({'success': False, 'message': 'Vui lòng nhập tên'}), 400

        if not msv:
            return jsonify({'success': False, 'message': 'Vui lòng nhập MSV'}), 400
        
        if class_name == '':
            return jsonify({'success': False, 'message': 'Class name is required'}), 400

        if db_service.get_face_by_msv(msv, class_name):
            return jsonify({'success': False, 'message': 'MSV đã tồn tại trong lớp này'}), 400
        
        file = request.files['image']
        
        file_bytes = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'success': False, 'message': 'Failed to decode image'}), 400
        
        # Detect face
        faces = face_service.detect_faces(image)
        
        if len(faces) == 0:
            return jsonify({'success': False, 'message': 'No face detected in image'}), 400
        
        if len(faces) > 1:
            return jsonify({'success': False, 'message': 'Multiple faces detected. Please upload image with only one face'}), 400
        
        face_box = faces[0]
        encoding = face_service.extract_face_encoding(image, face_box)
        
        if encoding is None:
            return jsonify({'success': False, 'message': 'Failed to extract face encoding'}), 500
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_filename = f"{msv}_{timestamp}.jpg"
        image_path = UPLOAD_FOLDER / image_filename
        cv2.imwrite(str(image_path), image)
        
        face_id = db_service.create_face(name, msv, encoding, str(image_path), session['user_id'], class_name)
        
        if face_id:
            return jsonify({'success': True, 'message': f'Đăng ký thành công: {name} (MSV: {msv})'})
        else:
            return jsonify({'success': False, 'message': 'Failed to save face data'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/classes', methods=['GET'])
def api_get_classes():
    """Get all classes"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        classes = db_service.get_all_classes()
        return jsonify({'success': True, 'classes': classes})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/classes/<class_name>', methods=['DELETE'])
def api_delete_class(class_name):
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        if not class_name:
            return jsonify({'success': False, 'message': 'Thiếu tên lớp'}), 400

        result = db_service.delete_class(class_name)
        if result is None:
            return jsonify({'success': False, 'message': 'Xóa lớp thất bại'}), 500

        return jsonify({'success': True, 'deleted': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance', methods=['GET'])
def api_get_attendance():
    """Get attendance records by class"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        class_name = request.args.get('class_name')
        
        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400
        
        attendance = db_service.get_attendance_by_class(class_name)
        return jsonify({'success': True, 'attendance': attendance})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance-summary', methods=['GET'])
def api_get_attendance_summary():
    """Get attendance summary by class"""
    global browser_recognized_faces, browser_session_start
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        class_name = request.args.get('class_name')
        attendance_type = request.args.get('attendance_type')
        
        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400
        
        use_session = request.args.get('session') == '1'
        
        if use_session and browser_session_start:
            summary = get_browser_session_summary(class_name)
        elif use_session and rtsp_service.is_running and rtsp_service.session_start_time:
            if class_name == rtsp_service.class_name and attendance_type == rtsp_service.attendance_type:
                summary = rtsp_service.get_session_summary()
            else:
                summary = db_service.get_attendance_summary(class_name, attendance_type)
        else:
            summary = db_service.get_attendance_summary(class_name, attendance_type)
        return jsonify({'success': True, 'summary': summary})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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

@app.route('/api/attendance-sessions', methods=['GET'])
def api_get_attendance_sessions():
    """Get attendance sessions by class"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        class_name = request.args.get('class_name')
        
        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400
        
        sessions = db_service.get_attendance_sessions_by_class(class_name)
        return jsonify({'success': True, 'sessions': sessions})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance-sessions', methods=['DELETE'])
def api_delete_attendance_sessions():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        data = request.get_json() or {}
        session_ids = data.get('session_ids', [])

        if not session_ids:
            return jsonify({'success': False, 'message': 'Session ids are required'}), 400

        deleted_count = db_service.delete_attendance_sessions(session_ids)
        return jsonify({'success': True, 'deleted': deleted_count})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance-sessions/export', methods=['POST'])
def api_export_attendance_sessions():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        data = request.get_json() or {}
        session_ids = data.get('session_ids', [])

        if not session_ids:
            return jsonify({'success': False, 'message': 'Session ids are required'}), 400

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
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance-session-detail', methods=['GET'])
def api_get_attendance_session_detail():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'success': False, 'message': 'Session id is required'}), 400

        session_record = db_service.get_attendance_session_by_id(session_id)
        if not session_record:
            return jsonify({'success': False, 'message': 'Session not found'}), 404

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
        present_map = {}
        for record in records:
            name = record.get('name') or ''
            normalized = db_service._normalize_name(name)
            if not normalized:
                continue
            existing = present_map.get(normalized)
            if existing is None or record.get('timestamp') > existing.get('timestamp'):
                present_map[normalized] = record

        all_faces = db_service.get_faces_by_class(class_name)
        face_msv_map = {db_service._normalize_name(f.get('name')): f.get('msv') for f in all_faces if f.get('name')}
        
        present_faces = []
        if present_map:
            for record in present_map.values():
                name = record.get('name')
                normalized = db_service._normalize_name(name)
                present_faces.append({
                    'name': name,
                    'msv': face_msv_map.get(normalized, ''),
                    'face_image': record.get('face_image')
                })
        elif session_record.get('present_faces'):
            pf = session_record.get('present_faces', [])
            for face in pf:
                name = face.get('name')
                normalized = db_service._normalize_name(name)
                present_faces.append({
                    'name': name,
                    'msv': face_msv_map.get(normalized, ''),
                    'face_image': face.get('face_image')
                })

        all_students = db_service.get_class_students(class_name)
        present_normalized = {db_service._normalize_name(face.get('name')) for face in present_faces if face.get('name')}
        absent_names = []
        for name in all_students:
            if db_service._normalize_name(name) not in present_normalized:
                absent_names.append(name)

        total_students = len(all_students)
        present_count = len(present_faces)
        absent_count = len(absent_names)

        return jsonify({
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
            'absent_names': absent_names
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/class-students', methods=['GET'])
def api_get_class_students():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        class_name = request.args.get('class_name')
        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400

        students = db_service.get_faces_by_class(class_name)
        return jsonify({'success': True, 'students': students})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/class-students/<student_id>', methods=['PUT'])
def api_update_class_student(student_id):
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        data = request.get_json() or {}
        name = data.get('name')
        if not name:
            return jsonify({'success': False, 'message': 'Name is required'}), 400

        updated = db_service.update_face_name(student_id, name)
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Update failed'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/class-students/<student_id>', methods=['DELETE'])
def api_delete_class_student(student_id):
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        deleted = db_service.delete_face(student_id)
        if deleted:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Delete failed'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/faces', methods=['GET'])
def api_get_faces():
    """Get all registered faces"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
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
        
        return jsonify({'success': True, 'faces': face_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/start-rtsp', methods=['POST'])
def api_start_rtsp():
    """Start RTSP stream"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        data = request.get_json()
        rtsp_url = data.get('rtsp_url')
        class_name = data.get('class_name')
        attendance_type = data.get('attendance_type', 'in') # Default to 'in'
        
        if not rtsp_url:
            return jsonify({'success': False, 'message': 'RTSP URL is required'}), 400
        
        success = rtsp_service.start_stream(rtsp_url, class_name, session['user_id'], attendance_type)
        
        if success:
            return jsonify({'success': True, 'message': 'RTSP stream started'})
        else:
            return jsonify({'success': False, 'message': 'Failed to start RTSP stream'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/stop-rtsp', methods=['GET'])
def api_stop_rtsp():
    """Stop RTSP stream"""
    try:
        rtsp_service.stop_stream()
        return jsonify({'success': True, 'message': 'RTSP stream stopped'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/video-feed')
def video_feed():
    """Video feed endpoint"""
    def generate():
        while rtsp_service.is_running:
            frame = rtsp_service.get_current_frame()
            if frame is not None:
                _, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/recognized-faces', methods=['GET'])
def api_recognized_faces():
    """Get currently recognized faces"""
    try:
        faces = rtsp_service.get_recognized_faces()
        return jsonify({'success': True, 'faces': faces})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

browser_recognized_faces = {}
browser_session_start = None

@app.route('/api/browser-session/start', methods=['POST'])
def api_browser_session_start():
    """Start browser camera session"""
    global browser_recognized_faces, browser_session_start
    browser_recognized_faces = {}
    browser_session_start = datetime.now()
    return jsonify({'success': True})

@app.route('/api/browser-session/stop', methods=['POST'])
def api_browser_session_stop():
    """Stop browser camera session and save attendance"""
    global browser_recognized_faces, browser_session_start
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        data = request.get_json() or {}
        class_name = data.get('class_name')
        attendance_type = data.get('attendance_type', 'in')

        if class_name and browser_session_start:
            end_time = datetime.now()
            present_faces = []
            for face_data in browser_recognized_faces.values():
                present_faces.append({
                    'name': face_data.get('name'),
                    'face_image': face_data.get('face_image')
                })

            summary = db_service.get_attendance_summary_in_range(
                class_name, attendance_type, browser_session_start, end_time
            )
            db_service.create_attendance_session(
                class_name, attendance_type, session['user_id'],
                browser_session_start, end_time,
                summary.get('present', 0), summary.get('total', 0),
                summary.get('absent', 0), present_faces=present_faces
            )

        browser_recognized_faces = {}
        browser_session_start = None
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/recognize-frame', methods=['POST'])
def api_recognize_frame():
    """Recognize faces from browser camera frame"""
    global browser_recognized_faces
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        data = request.get_json()
        image_data = data.get('image')
        class_name = data.get('class_name')
        attendance_type = data.get('attendance_type', 'in')

        if not image_data or ',' not in image_data:
            return jsonify({'success': False, 'message': 'Invalid image'}), 400

        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({'success': False, 'message': 'Failed to decode image'}), 400

        faces = face_service.detect_faces(frame)
        if not faces:
            return jsonify({'success': True, 'faces': list(browser_recognized_faces.values())})

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
                        name, class_name, session['user_id'], attendance_type,
                        attendance_time=datetime.now(), allow_duplicate=True,
                        face_image=face_image_base64
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

        return jsonify({'success': True, 'faces': list(browser_recognized_faces.values())})

    except Exception as e:
        print(f"Error in recognize-frame: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Schedule API endpoints
@app.route('/api/schedules', methods=['POST'])
def api_create_schedule():
    """Create a new attendance schedule"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        data = request.get_json()
        class_name = data.get('class_name')
        attendance_type = data.get('attendance_type', 'in')
        rtsp_url = data.get('rtsp_url', '0')
        start_hour = data.get('start_hour')
        start_minute = data.get('start_minute', 0)
        duration_minutes = data.get('duration_minutes', 15)
        total_days = data.get('total_days', 1)

        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400
        if start_hour is None:
            return jsonify({'success': False, 'message': 'Start hour is required'}), 400

        schedule_id = db_service.create_schedule(
            class_name, attendance_type, rtsp_url,
            int(start_hour), int(start_minute),
            int(duration_minutes), int(total_days),
            session['user_id']
        )

        if schedule_id:
            return jsonify({'success': True, 'schedule_id': schedule_id})
        return jsonify({'success': False, 'message': 'Failed to create schedule'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/schedules', methods=['GET'])
def api_get_schedules():
    """Get schedules for a class"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        class_name = request.args.get('class_name')
        if not class_name:
            return jsonify({'success': False, 'message': 'Class name is required'}), 400

        schedules = db_service.get_schedules_by_class(class_name)
        scheduler_status = scheduler.get_status()
        return jsonify({'success': True, 'schedules': schedules, 'scheduler': scheduler_status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/schedules/<schedule_id>/toggle', methods=['PUT'])
def api_toggle_schedule(schedule_id):
    """Toggle schedule active status"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        result = db_service.toggle_schedule(schedule_id)
        if result is None:
            return jsonify({'success': False, 'message': 'Schedule not found'}), 404
        return jsonify({'success': True, 'active': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/schedules/<schedule_id>', methods=['DELETE'])
def api_delete_schedule(schedule_id):
    """Delete a schedule"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        deleted = db_service.delete_schedule(schedule_id)
        if deleted:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Delete failed'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print("Face Recognition Attendance System")
    print("="*50)
    print("\nStarting Flask application...")
    print("Access the application at: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Start the scheduler
    scheduler.start()
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)

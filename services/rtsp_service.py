import cv2
import threading
import time
import numpy as np
import base64
from services.face_recognition_service import face_service
from services.database_service import db_service

class RTSPService:
    """Service for handling RTSP stream and real-time face recognition"""
    
    def __init__(self):
        self.stream = None
        self.is_running = False
        self.thread = None
        self.current_frame = None
        self.recognized_faces = []
        self.recognized_faces_dict = {}  # Store persistent recognized faces
        self.rtsp_url = None
        self.class_name = None
        self.user_id = None
        self.attendance_recorded_today = set()  # Track attendance recorded today
        self.confidence_threshold = 70.0  # Minimum confidence to update recognized faces
        self.session_start_time = None
    
    def start_stream(self, rtsp_url, class_name=None, user_id=None, attendance_type='in'):
        """Start RTSP stream or webcam"""
        try:
            self.class_name = class_name
            self.user_id = user_id
            self.attendance_type = attendance_type
            self.attendance_recorded_today = set()  # Reset attendance tracking
            from datetime import datetime
            self.session_start_time = datetime.now()
            
            # Check if we should use webcam (rtsp_url is "0" or empty)
            use_webcam = not rtsp_url or rtsp_url.strip() == '0' or rtsp_url.strip() == ''
            
            if use_webcam:
                self.rtsp_url = '0'
                self.stream = None
                camera_indices = [0, 1, 2]
                for index in camera_indices:
                    self.stream = cv2.VideoCapture(index)
                    print(f"✓ Attempting to open webcam (camera index {index})...")
                    if self.stream.isOpened():
                        break
            else:
                # Use RTSP stream
                self.rtsp_url = rtsp_url
                self.stream = cv2.VideoCapture(rtsp_url)
                print(f"✓ Attempting to open RTSP stream: {rtsp_url}")
            
            if not self.stream.isOpened():
                source_name = "webcam" if use_webcam else f"RTSP stream ({rtsp_url})"
                print(f"✗ Failed to open {source_name}")
                return False
            
            self.is_running = True
            self.thread = threading.Thread(target=self._process_stream, daemon=True)
            self.thread.start()
            
            if use_webcam:
                print("✓ Webcam started successfully")
            else:
                print(f"✓ RTSP stream started: {rtsp_url}")
            
            if class_name:
                print(f"✓ Attendance tracking enabled for class: {class_name}")
            return True
            
        except Exception as e:
            print(f"✗ Error starting stream: {e}")
            return False
    
    def stop_stream(self):
        """Stop RTSP stream"""
        if self.class_name and self.user_id and self.session_start_time:
            from datetime import datetime
            end_time = datetime.now()
            present_faces_map = {}
            for face_data in self.recognized_faces_dict.values():
                name = face_data.get('name')
                class_name_for_face = face_data.get('class_name')
                if name and (class_name_for_face == self.class_name or class_name_for_face is None):
                    normalized = db_service._normalize_name(name)
                    if normalized and normalized not in present_faces_map:
                        present_faces_map[normalized] = {
                            'name': name,
                            'face_image': face_data.get('face_image')
                        }
                    db_service.create_attendance(
                        name,
                        self.class_name,
                        self.user_id,
                        self.attendance_type,
                        attendance_time=end_time,
                        allow_duplicate=True,
                        face_image=face_data.get('face_image')
                    )
            present_faces = list(present_faces_map.values())
            summary = db_service.get_attendance_summary_in_range(
                self.class_name,
                self.attendance_type,
                self.session_start_time,
                end_time
            )
            db_service.create_attendance_session(
                self.class_name,
                self.attendance_type,
                self.user_id,
                self.session_start_time,
                end_time,
                summary.get('present', 0),
                summary.get('total', 0),
                summary.get('absent', 0),
                present_faces=present_faces
            )
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.stream:
            self.stream.release()
        self.stream = None
        self.current_frame = None
        self.recognized_faces = []
        self.recognized_faces_dict = {}  # Clear recognized faces dict
        self.class_name = None
        self.user_id = None
        self.attendance_recorded_today = set()
        self.session_start_time = None
        print("✓ RTSP stream stopped")
    
    def _process_stream(self):
        """Process RTSP stream frames"""
        frame_skip = 5  # Process every 5th frame for performance
        frame_count = 0
        
        while self.is_running:
            try:
                ret, frame = self.stream.read()
                if not ret:
                    print("✗ Failed to read frame from stream")
                    time.sleep(0.1)
                    continue
                
                frame_count += 1
                
                # Skip frames for performance
                if frame_count % frame_skip != 0:
                    self.current_frame = frame
                    continue
                
                # Detect and recognize faces
                self._recognize_faces_in_frame(frame)
                self.current_frame = frame
                
                time.sleep(0.03)  # ~30 FPS
                
            except Exception as e:
                print(f"Error processing stream: {e}")
                time.sleep(0.1)
    
    def _recognize_faces_in_frame(self, frame):
        """Detect and recognize faces in a frame"""
        try:
            # Detect faces
            faces = face_service.detect_faces(frame)
            
            if not faces or len(faces) == 0:
                # Keep previous results, don't clear
                return
            
            # Get known faces from database
            known_faces = db_service.get_all_faces()
            
            # Track new recognitions
            new_recognitions = {}
            
            for face_box in faces:
                # Extract face encoding
                encoding = face_service.extract_face_encoding(frame, face_box)
                
                if encoding is not None:
                    match, confidence = face_service.identify_face(encoding, known_faces)
                    name = match.get('name') if match else None
                    msv = match.get('msv') if match else None
                    
                    x, y, w, h = face_box
                    
                    if match and confidence < self.confidence_threshold:
                        continue  # Skip low confidence recognitions
                    
                    normalized_name = db_service._normalize_name(name) if name else ''
                    person_key = msv or name or f"unknown_{x}_{y}"
                    
                    # Check if we already have this person with higher confidence
                    existing_confidence = None
                    existing_db_image = None
                    if person_key in self.recognized_faces_dict:
                        existing_confidence = self.recognized_faces_dict[person_key].get('confidence', 0)
                        existing_db_image = self.recognized_faces_dict[person_key].get('db_image')
                    
                    # Only update if this is a new person or confidence is higher
                    if existing_confidence is None or confidence > existing_confidence:
                        # Crop face from frame
                        face_crop = frame[y:y+h, x:x+w]
                        face_image_base64 = None
                        
                        if face_crop.size > 0:
                            # Encode cropped face as base64
                            _, buffer = cv2.imencode('.jpg', face_crop)
                            face_image_base64 = base64.b64encode(buffer).decode('utf-8')
                        
                        if name:
                            face_info = match
                            class_name_for_face = face_info.get('class_name') if face_info else None
                            if class_name_for_face is None:
                                class_name_for_face = self.class_name
                            
                            db_image_base64 = None
                            if face_info and face_info.get('image_path'):
                                try:
                                    import os
                                    img_path = face_info['image_path']
                                    if not os.path.isabs(img_path):
                                        img_path = os.path.join(os.getcwd(), img_path)
                                    if os.path.exists(img_path):
                                        db_img = cv2.imread(img_path)
                                        if db_img is not None:
                                            _, db_buffer = cv2.imencode('.jpg', db_img)
                                            db_image_base64 = base64.b64encode(db_buffer).decode('utf-8')
                                except:
                                    pass
                            
                            attendance_key = msv or normalized_name
                            if (self.class_name and 
                                self.user_id and 
                                class_name_for_face == self.class_name and
                                attendance_key not in self.attendance_recorded_today):
                                
                                from datetime import datetime
                                attendance_id = db_service.create_attendance(
                                    name, 
                                    self.class_name, 
                                    self.user_id,
                                    self.attendance_type,
                                    attendance_time=datetime.now(),
                                    allow_duplicate=True,
                                    face_image=face_image_base64
                                )
                                
                                if attendance_id: 
                                    self.attendance_recorded_today.add(attendance_key)
                                    print(f"✓ Attendance recorded: {name} - {self.class_name}")
                            
                            new_recognitions[person_key] = {
                                'name': name,
                                'msv': msv,
                                'confidence': round(confidence, 2),
                                'class_name': class_name_for_face,
                                'attendance_type': self.attendance_type,
                                'box': {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)},
                                'face_image': face_image_base64,
                                'db_image': db_image_base64
                            }
                    if person_key in self.recognized_faces_dict and existing_db_image is None and 'db_image' in new_recognitions.get(person_key, {}):
                        if new_recognitions[person_key].get('db_image'):
                            self.recognized_faces_dict[person_key]['db_image'] = new_recognitions[person_key]['db_image']
            
            # Update recognized_faces_dict with new or better recognitions
            for key, face_data in new_recognitions.items():
                self.recognized_faces_dict[key] = face_data
            
            # Remove faces that are no longer detected (optional - you can keep them for a while)
            # For now, we'll keep all previously recognized faces
            
            # Convert dict to list for API response
            self.recognized_faces = list(self.recognized_faces_dict.values())
            
        except Exception as e:
            print(f"Error recognizing faces: {e}")
            # Don't clear on error, keep previous results
    
    def get_current_frame(self):
        """Get current frame without face boxes"""
        if self.current_frame is None:
            return None
        
        return self.current_frame.copy()
    
    def get_recognized_faces(self):
        """Get list of currently recognized faces"""
        return self.recognized_faces

    def get_session_summary(self):
        if not self.class_name:
            return {'present': 0, 'absent': 0, 'total': 0}
        student_names = db_service.get_class_students(self.class_name)
        normalized_students = {db_service._normalize_name(name) for name in student_names if name}
        present_normalized = set()
        for face_data in self.recognized_faces_dict.values():
            name = face_data.get('name')
            class_name_for_face = face_data.get('class_name') or self.class_name
            if name and class_name_for_face == self.class_name:
                present_normalized.add(db_service._normalize_name(name))
        present = len(present_normalized & normalized_students)
        total = len(normalized_students)
        absent = total - present
        if absent < 0:
            absent = 0
        return {'present': present, 'absent': absent, 'total': total}

# Global RTSP service instance
rtsp_service = RTSPService()

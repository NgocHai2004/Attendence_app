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
            self.session_start_time = datetime.utcnow()
            
            # Check if we should use webcam (rtsp_url is "0" or empty)
            use_webcam = not rtsp_url or rtsp_url.strip() == '0' or rtsp_url.strip() == ''
            
            if use_webcam:
                # Use webcam (camera index 0)
                self.rtsp_url = '0'  # Store as "0" to indicate webcam
                self.stream = cv2.VideoCapture(0)
                print("✓ Attempting to open webcam (camera index 0)...")
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
            end_time = datetime.utcnow()
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
                summary.get('absent', 0)
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
                    # Identify face
                    name, confidence = face_service.identify_face(encoding, known_faces)
                    
                    x, y, w, h = face_box
                    
                    # Only process if confidence is above threshold
                    if name and confidence < self.confidence_threshold:
                        continue  # Skip low confidence recognitions
                    
                    # Create a key for this person (name or position-based for Unknown)
                    person_key = name if name else f"unknown_{x}_{y}"
                    
                    # Check if we already have this person with higher confidence
                    existing_confidence = None
                    if person_key in self.recognized_faces_dict:
                        existing_confidence = self.recognized_faces_dict[person_key].get('confidence', 0)
                    
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
                            # Get face info to check class
                            face_info = None
                            for face in known_faces:
                                if face.get('name') == name:
                                    face_info = face
                                    break
                            
                            class_name_for_face = face_info.get('class_name') if face_info else None
                            
                            # Record attendance if class matches and not already recorded today
                            if (self.class_name and 
                                self.user_id and 
                                class_name_for_face == self.class_name and
                                name not in self.attendance_recorded_today):
                                
                                attendance_id = db_service.create_attendance(
                                    name, 
                                    self.class_name, 
                                    self.user_id,
                                    self.attendance_type
                                )
                                
                                if attendance_id: 
                                    self.attendance_recorded_today.add(name)
                                    print(f"✓ Attendance recorded: {name} - {self.class_name}")
                            
                            new_recognitions[person_key] = {
                                'name': name,
                                'confidence': round(confidence, 2),
                                'class_name': class_name_for_face,
                                'attendance_type': self.attendance_type,
                                # 'box': {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)},
                                'face_image': face_image_base64
                            }
            
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
        """Get current frame with face boxes drawn"""
        if self.current_frame is None:
            return None
        
        frame = self.current_frame.copy()
        
        # Draw bounding boxes and names
        for face in self.recognized_faces:
            box = face['box']
            name = face['name']
            confidence = face['confidence']
            
            x, y, w, h = box['x'], box['y'], box['w'], box['h']
            
            # Choose color based on recognition
            color = (0, 255, 0) if name != 'Unknown' else (0, 0, 255)
            
            # Draw rectangle
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            
            # Draw label
            label = f"{name} ({confidence}%)" if name != 'Unknown' else "Unknown"
            cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, color, 2)
        
        return frame
    
    def get_recognized_faces(self):
        """Get list of currently recognized faces"""
        return self.recognized_faces

# Global RTSP service instance
rtsp_service = RTSPService()

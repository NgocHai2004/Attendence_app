import os
import unicodedata
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
import bcrypt
from bson import ObjectId

# Load environment variables
load_dotenv()

class DatabaseService:
    """Service for MongoDB operations"""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.users_collection = None
        self.faces_collection = None
        self.attendance_sessions_collection = None
        self.schedules_collection = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB"""
        try:
            mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
            db_name = os.getenv('DATABASE_NAME', 'attendance_app')
            
            self.client = MongoClient(mongodb_uri)
            self.db = self.client[db_name]
            self.users_collection = self.db['users']
            self.faces_collection = self.db['faces']
            self.attendance_collection = self.db['attendance']
            self.attendance_sessions_collection = self.db['attendance_sessions']
            self.schedules_collection = self.db['schedules']
            
            # Create indexes
            self.users_collection.create_index('email', unique=True)
            self.users_collection.create_index('username', unique=True)
            self.faces_collection.create_index('user_id')
            self.faces_collection.create_index('class_name')
            self.faces_collection.create_index('msv')
            self.attendance_collection.create_index('class_name')
            self.attendance_collection.create_index('date')
            self.attendance_collection.create_index([('class_name', 1), ('date', -1)])
            self.attendance_sessions_collection.create_index('class_name')
            self.attendance_sessions_collection.create_index('end_time')
            self.schedules_collection.create_index('class_name')
            self.schedules_collection.create_index('active')
            
            print("✓ Connected to MongoDB successfully")
        except Exception as e:
            print(f"✗ Error connecting to MongoDB: {e}")
            raise

    def _normalize_name(self, name):
        if not name:
            return ''
        normalized = unicodedata.normalize('NFD', name)
        normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
        return normalized.strip().lower()
    
    # User operations
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            # Hash password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            user_data = {
                'username': username,
                'email': email,
                'password': hashed_password.decode('utf-8'),
                'created_at': None
            }
            
            
            user_data['created_at'] = datetime.utcnow()
            
            result = self.users_collection.insert_one(user_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    def get_user_by_email(self, email):
        """Get user by email"""
        return self.users_collection.find_one({'email': email})
    
    def get_user_by_username(self, username):
        """Get user by username"""
        return self.users_collection.find_one({'username': username})
    
    def verify_password(self, plain_password, hashed_password):
        """Verify password"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    # Face operations
    def create_face(self, name, msv, encoding, image_path, user_id, class_name=None):
        """Create a new face entry"""
        try:
            
            face_data = {
                'name': name,
                'msv': msv,
                'encoding': encoding.tolist() if hasattr(encoding, 'tolist') else encoding,
                'image_path': image_path,
                'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
                'class_name': class_name,
                'created_at': datetime.utcnow()
            }
            
            result = self.faces_collection.insert_one(face_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating face: {e}")
            return None

    def get_face_by_msv(self, msv, class_name=None):
        try:
            query = {'msv': msv}
            if class_name:
                query['class_name'] = class_name
            return self.faces_collection.find_one(query)
        except Exception as e:
            print(f"Error getting face by msv: {e}")
            return None
    
    def get_all_faces(self):
        """Get all face encodings"""
        return list(self.faces_collection.find())
    
    def get_faces_by_user(self, user_id):
        """Get all faces registered by a user"""

        return list(self.faces_collection.find({'user_id': ObjectId(user_id)}))
    
    def delete_face(self, face_id):
        """Delete a face entry"""

        result = self.faces_collection.delete_one({'_id': ObjectId(face_id)})
        return result.deleted_count > 0

    def get_faces_by_class(self, class_name):
        try:
            faces = self.faces_collection.find({'class_name': class_name})
            result = []
            for face in faces:
                result.append({
                    'id': str(face['_id']),
                    'name': face.get('name', ''),
                    'msv': face.get('msv', ''),
                    'class_name': face.get('class_name'),
                    'encoding': face.get('encoding'),
                    'image_path': face.get('image_path')
                })
            return result
        except Exception as e:
            print(f"Error getting faces by class: {e}")
            return []

    def update_face_name(self, face_id, new_name):
        try:

            result = self.faces_collection.update_one(
                {'_id': ObjectId(face_id)},
                {'$set': {'name': new_name}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating face name: {e}")
            return False
    
    # Class operations
    def get_all_classes(self):
        """Get all unique class names"""
        classes = self.faces_collection.distinct('class_name')
        return [c for c in classes if c]  # Filter out None values

    def delete_class(self, class_name):
        try:
            faces_result = self.faces_collection.delete_many({'class_name': class_name})
            attendance_result = self.attendance_collection.delete_many({'class_name': class_name})
            sessions_result = self.attendance_sessions_collection.delete_many({'class_name': class_name})
            return {
                'faces_deleted': faces_result.deleted_count,
                'attendance_deleted': attendance_result.deleted_count,
                'sessions_deleted': sessions_result.deleted_count
            }
        except Exception as e:
            print(f"Error deleting class: {e}")
            return None
    
    # Attendance operations
    def create_attendance(self, name, class_name, user_id, attendance_type='in', attendance_time=None, allow_duplicate=False, face_image=None):
        try:
            
            now = attendance_time or datetime.now()
            if not allow_duplicate:
                today_start = datetime(now.year, now.month, now.day)
                today_end = today_start + timedelta(days=1)
                
                existing = self.attendance_collection.find_one({
                    'name': name,
                    'class_name': class_name,
                    'attendance_type': attendance_type,
                    'timestamp': {
                        '$gte': today_start,
                        '$lt': today_end
                    }
                })
                
                if existing:
                    return str(existing['_id'])
            
            attendance_data = {
                'name': name,
                'class_name': class_name,
                'attendance_type': attendance_type,
                'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
                'date': now.date(),
                'timestamp': now
            }
            if face_image:
                attendance_data['face_image'] = face_image
            
            result = self.attendance_collection.insert_one(attendance_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating attendance: {e}")
            return None
    
    def get_attendance_by_class(self, class_name, limit=100):
        """Get attendance records for a specific class"""
        try:

            
            attendance_records = self.attendance_collection.find(
                {'class_name': class_name}
            ).sort('timestamp', -1).limit(limit)
            
            result = []
            for record in attendance_records:
                date_value = record.get('date')
                timestamp_value = record.get('timestamp')
                
                # Handle date formatting
                if isinstance(date_value, datetime):
                    date_str = date_value.date().isoformat()
                elif hasattr(date_value, 'isoformat'):
                    date_str = date_value.isoformat()
                else:
                    date_str = str(date_value) if date_value else None
                
                # Handle timestamp formatting
                if isinstance(timestamp_value, datetime):
                    timestamp_str = timestamp_value.isoformat()
                elif timestamp_value:
                    timestamp_str = str(timestamp_value)
                else:
                    timestamp_str = None
                
                result.append({
                    'id': str(record['_id']),
                    'name': record['name'],
                    'class_name': record['class_name'],
                    'date': date_str,
                    'timestamp': timestamp_str
                })
            
            return result
        except Exception as e:
            print(f"Error getting attendance: {e}")
            return []

    def get_attendance_summary(self, class_name, attendance_type=None):
        try:


            student_msvs = self.faces_collection.distinct('msv', {'class_name': class_name})
            student_msvs = {msv for msv in student_msvs if msv}
            total_students = len(student_msvs)

            now = datetime.now()
            today_start = datetime(now.year, now.month, now.day)
            today_end = today_start + timedelta(days=1)

            summary_query = {
                'class_name': class_name,
                'timestamp': {
                    '$gte': today_start,
                    '$lt': today_end
                }
            }
            if attendance_type:
                summary_query['attendance_type'] = attendance_type

            present_records = list(self.attendance_collection.find(summary_query, {'name': 1}))
            present_msvs = set()
            for record in present_records:
                name = record.get('name')
                if name:
                    face = self.faces_collection.find_one({'name': name, 'class_name': class_name}, {'msv': 1})
                    if face and face.get('msv'):
                        present_msvs.add(face['msv'])

            present_students = len(present_msvs & student_msvs)
            absent_students = total_students - present_students
            if absent_students < 0:
                absent_students = 0

            return {
                'present': present_students,
                'absent': absent_students,
                'total': total_students
            }
        except Exception as e:
            print(f"Error getting attendance summary: {e}")
            return {
                'present': 0,
                'absent': 0,
                'total': 0
            }

    def get_attendance_summary_in_range(self, class_name, attendance_type, start_time, end_time):
        try:
            student_msvs = self.faces_collection.distinct('msv', {'class_name': class_name})
            student_msvs = {msv for msv in student_msvs if msv}
            total_students = len(student_msvs)

            summary_query = {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'timestamp': {
                    '$gte': start_time,
                    '$lte': end_time
                }
            }

            present_records = list(self.attendance_collection.find(summary_query, {'name': 1}))
            present_msvs = set()
            for record in present_records:
                name = record.get('name')
                if name:
                    face = self.faces_collection.find_one({'name': name, 'class_name': class_name}, {'msv': 1})
                    if face and face.get('msv'):
                        present_msvs.add(face['msv'])

            present_students = len(present_msvs & student_msvs)
            absent_students = total_students - present_students
            if absent_students < 0:
                absent_students = 0

            return {
                'present': present_students,
                'absent': absent_students,
                'total': total_students
            }
        except Exception as e:
            print(f"Error getting attendance summary in range: {e}")
            return {
                'present': 0,
                'absent': 0,
                'total': 0
            }

    def create_attendance_session(self, class_name, attendance_type, user_id, start_time, end_time, present, total, absent, present_faces=None):
        try:

            session_data = {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
                'start_time': start_time,
                'end_time': end_time,
                'present': present,
                'absent': absent,
                'total': total
            }
            if present_faces:
                session_data['present_faces'] = present_faces
            result = self.attendance_sessions_collection.insert_one(session_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating attendance session: {e}")
            return None

    def get_attendance_sessions_by_class(self, class_name, limit=50):
        try:

            sessions = self.attendance_sessions_collection.find(
                {'class_name': class_name}
            ).sort('end_time', -1).limit(limit)

            result = []
            for record in sessions:
                start_time = record.get('start_time')
                end_time = record.get('end_time')
                attendance_type = record.get('attendance_type')

                student_names = self.get_class_students(class_name)
                normalized_students = {self._normalize_name(name) for name in student_names if name}
                total_students = len(normalized_students)

                present_faces = record.get('present_faces') or []
                if present_faces:
                    present_normalized = {self._normalize_name(face.get('name')) for face in present_faces if face.get('name')}
                else:
                    records_in_range = self.get_attendance_records_in_range(
                        class_name,
                        attendance_type,
                        start_time,
                        end_time
                    )
                    present_normalized = {self._normalize_name(r.get('name')) for r in records_in_range if r.get('name')}

                present_count = len(present_normalized & normalized_students)
                absent_count = total_students - present_count
                if absent_count < 0:
                    absent_count = 0

                if isinstance(start_time, datetime):
                    start_str = start_time.isoformat()
                else:
                    start_str = str(start_time) if start_time else None

                if isinstance(end_time, datetime):
                    end_str = end_time.isoformat()
                else:
                    end_str = str(end_time) if end_time else None

                result.append({
                    'id': str(record['_id']),
                    'class_name': record.get('class_name'),
                    'attendance_type': attendance_type,
                    'start_time': start_str,
                    'end_time': end_str,
                    'present': present_count,
                    'absent': absent_count,
                    'total': total_students
                })
            return result
        except Exception as e:
            print(f"Error getting attendance sessions: {e}")
            return []

    def get_attendance_session_by_id(self, session_id):
        try:

            record = self.attendance_sessions_collection.find_one({'_id': ObjectId(session_id)})
            if not record:
                return None
            return {
                'id': str(record['_id']),
                'class_name': record.get('class_name'),
                'attendance_type': record.get('attendance_type'),
                'start_time': record.get('start_time'),
                'end_time': record.get('end_time'),
                'present': record.get('present', 0),
                'absent': record.get('absent', 0),
                'total': record.get('total', 0),
                'present_faces': record.get('present_faces', [])
            }
        except Exception as e:
            print(f"Error getting attendance session by id: {e}")
            return None

    def get_class_students(self, class_name):
        try:
            return list(self.faces_collection.distinct('name', {'class_name': class_name}))
        except Exception as e:
            print(f"Error getting class students: {e}")
            return []

    def get_attendance_names_in_range(self, class_name, attendance_type, start_time, end_time):
        try:
            return list(self.attendance_collection.distinct('name', {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'timestamp': {
                    '$gte': start_time,
                    '$lte': end_time
                }
            }))
        except Exception as e:
            print(f"Error getting attendance names in range: {e}")
            return []

    def get_attendance_records_in_range(self, class_name, attendance_type, start_time, end_time):
        try:
            records = self.attendance_collection.find({
                'class_name': class_name,
                'attendance_type': attendance_type,
                'timestamp': {
                    '$gte': start_time,
                    '$lte': end_time
                }
            }).sort('timestamp', 1)
            result = []
            for record in records:
                result.append({
                    'name': record.get('name'),
                    'face_image': record.get('face_image'),
                    'timestamp': record.get('timestamp')
                })
            return result
        except Exception as e:
            print(f"Error getting attendance records in range: {e}")
            return []

    def delete_attendance_sessions(self, session_ids):
        try:

            object_ids = [ObjectId(sid) for sid in session_ids]
            result = self.attendance_sessions_collection.delete_many({'_id': {'$in': object_ids}})
            return result.deleted_count
        except Exception as e:
            print(f"Error deleting attendance sessions: {e}")
            return 0

    # Schedule operations
    def create_schedule(self, class_name, attendance_type, rtsp_url, start_hour, start_minute, duration_minutes, total_days, user_id):
        """Create a new attendance schedule"""
        try:
            schedule_data = {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'rtsp_url': rtsp_url,
                'start_hour': start_hour,
                'start_minute': start_minute,
                'duration_minutes': duration_minutes,
                'total_days': total_days,
                'days_completed': 0,
                'active': True,
                'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
                'created_at': datetime.utcnow(),
                'last_run_date': None
            }
            result = self.schedules_collection.insert_one(schedule_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating schedule: {e}")
            return None

    def get_schedules_by_class(self, class_name):
        """Get all schedules for a class"""
        try:
            schedules = self.schedules_collection.find({'class_name': class_name}).sort('created_at', -1)
            result = []
            for s in schedules:
                result.append({
                    'id': str(s['_id']),
                    'class_name': s.get('class_name'),
                    'attendance_type': s.get('attendance_type', 'in'),
                    'rtsp_url': s.get('rtsp_url', '0'),
                    'start_hour': s.get('start_hour', 0),
                    'start_minute': s.get('start_minute', 0),
                    'duration_minutes': s.get('duration_minutes', 15),
                    'total_days': s.get('total_days', 1),
                    'days_completed': s.get('days_completed', 0),
                    'active': s.get('active', False),
                    'created_at': s.get('created_at').isoformat() if s.get('created_at') else None,
                    'last_run_date': str(s.get('last_run_date')) if s.get('last_run_date') else None
                })
            return result
        except Exception as e:
            print(f"Error getting schedules: {e}")
            return []

    def get_all_active_schedules(self):
        """Get all active schedules"""
        try:
            schedules = list(self.schedules_collection.find({'active': True}))
            result = []
            for s in schedules:
                result.append({
                    'id': str(s['_id']),
                    'class_name': s.get('class_name'),
                    'attendance_type': s.get('attendance_type', 'in'),
                    'rtsp_url': s.get('rtsp_url', '0'),
                    'start_hour': s.get('start_hour', 0),
                    'start_minute': s.get('start_minute', 0),
                    'duration_minutes': s.get('duration_minutes', 15),
                    'total_days': s.get('total_days', 1),
                    'days_completed': s.get('days_completed', 0),
                    'user_id': str(s.get('user_id')),
                    'last_run_date': s.get('last_run_date')
                })
            return result
        except Exception as e:
            print(f"Error getting active schedules: {e}")
            return []

    def update_schedule_after_run(self, schedule_id):
        """Update schedule after a successful run"""
        try:
            today = datetime.now().date()
            schedule = self.schedules_collection.find_one({'_id': ObjectId(schedule_id)})
            if not schedule:
                return False
            new_days_completed = schedule.get('days_completed', 0) + 1
            total_days = schedule.get('total_days', 1)
            update_data = {
                'days_completed': new_days_completed,
                'last_run_date': datetime(today.year, today.month, today.day)
            }
            if new_days_completed >= total_days:
                update_data['active'] = False
            self.schedules_collection.update_one(
                {'_id': ObjectId(schedule_id)},
                {'$set': update_data}
            )
            return True
        except Exception as e:
            print(f"Error updating schedule after run: {e}")
            return False

    def toggle_schedule(self, schedule_id):
        """Toggle schedule active status"""
        try:
            schedule = self.schedules_collection.find_one({'_id': ObjectId(schedule_id)})
            if not schedule:
                return False
            new_active = not schedule.get('active', False)
            self.schedules_collection.update_one(
                {'_id': ObjectId(schedule_id)},
                {'$set': {'active': new_active}}
            )
            return new_active
        except Exception as e:
            print(f"Error toggling schedule: {e}")
            return None

    def delete_schedule(self, schedule_id):
        """Delete a schedule"""
        try:
            result = self.schedules_collection.delete_one({'_id': ObjectId(schedule_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting schedule: {e}")
            return False

# Global database instance
db_service = DatabaseService()

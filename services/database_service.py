import os
import unicodedata
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
import bcrypt

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
            from datetime import datetime
            from bson import ObjectId
            
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
        from bson import ObjectId
        return list(self.faces_collection.find({'user_id': ObjectId(user_id)}))
    
    def delete_face(self, face_id):
        """Delete a face entry"""
        from bson import ObjectId
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
                    'class_name': face.get('class_name')
                })
            return result
        except Exception as e:
            print(f"Error getting faces by class: {e}")
            return []

    def update_face_name(self, face_id, new_name):
        try:
            from bson import ObjectId
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
            from datetime import datetime, timedelta
            from bson import ObjectId
            
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
            from datetime import datetime
            
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
            from datetime import datetime, timedelta

            student_names = self.faces_collection.distinct('name', {'class_name': class_name})
            normalized_students = {self._normalize_name(name) for name in student_names if name}
            total_students = len(normalized_students)

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

            present_names = self.attendance_collection.distinct('name', summary_query)
            normalized_present = {self._normalize_name(name) for name in present_names if name}

            present_students = len(normalized_present & normalized_students)
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
            student_names = self.faces_collection.distinct('name', {'class_name': class_name})
            normalized_students = {self._normalize_name(name) for name in student_names if name}
            total_students = len(normalized_students)

            summary_query = {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'timestamp': {
                    '$gte': start_time,
                    '$lte': end_time
                }
            }

            present_names = self.attendance_collection.distinct('name', summary_query)
            normalized_present = {self._normalize_name(name) for name in present_names if name}

            present_students = len(normalized_present & normalized_students)
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
            from bson import ObjectId
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
            from datetime import datetime
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
            from bson import ObjectId
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
            from bson import ObjectId
            object_ids = [ObjectId(sid) for sid in session_ids]
            result = self.attendance_sessions_collection.delete_many({'_id': {'$in': object_ids}})
            return result.deleted_count
        except Exception as e:
            print(f"Error deleting attendance sessions: {e}")
            return 0

# Global database instance
db_service = DatabaseService()

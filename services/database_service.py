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
    def create_user(self, username, email, password, role='user'):
        """Create a new user"""
        try:
            # Hash password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            user_data = {
                'username': username,
                'email': email,
                'password': hashed_password.decode('utf-8'),
                'role': role,
                'is_active': True,
                'created_at': datetime.utcnow()
            }
            
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
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        try:
            return self.users_collection.find_one({'_id': ObjectId(user_id)})
        except Exception as e:
            print(f"Error getting user by id: {e}")
            return None
    
    def verify_password(self, plain_password, hashed_password):
        """Verify password"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def get_all_users(self):
        """Get all users (for admin)"""
        try:
            users = self.users_collection.find({}, {'password': 0})  # Exclude password
            result = []
            for user in users:
                result.append({
                    'id': str(user['_id']),
                    'username': user.get('username', ''),
                    'email': user.get('email', ''),
                    'role': user.get('role', 'user'),
                    'is_active': user.get('is_active', True),
                    'created_at': user.get('created_at')
                })
            return result
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []
    
    def update_user(self, user_id, username=None, email=None, role=None, is_active=None):
        """Update user information"""
        try:
            update_data = {}
            if username is not None:
                update_data['username'] = username
            if email is not None:
                update_data['email'] = email
            if role is not None:
                update_data['role'] = role
            if is_active is not None:
                update_data['is_active'] = is_active
            
            if not update_data:
                return False
            
            result = self.users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating user: {e}")
            return False
    
    def update_user_password(self, user_id, new_password):
        """Update user password"""
        try:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            result = self.users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'password': hashed_password.decode('utf-8')}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating user password: {e}")
            return False
    
    def delete_user(self, user_id):
        """Delete a user"""
        try:
            result = self.users_collection.delete_one({'_id': ObjectId(user_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False
    
    def count_users(self):
        """Count total users"""
        try:
            return self.users_collection.count_documents({})
        except Exception as e:
            print(f"Error counting users: {e}")
            return 0
    
    def count_admin_users(self):
        """Count admin users"""
        try:
            return self.users_collection.count_documents({'role': 'admin'})
        except Exception as e:
            print(f"Error counting admin users: {e}")
            return 0
    
    def ensure_admin_exists(self):
        """Ensure at least one admin user exists, create default if none"""
        try:
            admin_count = self.count_admin_users()
            if admin_count == 0:
                # Create default admin user
                self.create_user(
                    username='admin',
                    email='admin@gmail.com',
                    password='admin@123',
                    role='admin'
                )
                print("✓ Created default admin user (Email: admin@gmail.com / Password: admin@123)")
                return True
            else:
                # Check if old admin with email 'admin' exists and update to new email
                old_admin = self.get_user_by_email('admin')
                if old_admin:
                    # Update old admin email to admin@gmail.com
                    self.users_collection.update_one(
                        {'_id': old_admin['_id']},
                        {'$set': {'email': 'admin@gmail.com'}}
                    )
                    print("✓ Updated admin email from 'admin' to 'admin@gmail.com'")
                    return True
            return False
        except Exception as e:
            print(f"Error ensuring admin exists: {e}")
            return False
    
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
    
    def get_all_students(self, search_msv=None, sort_by='name'):
        """Get all students from all classes, sorted alphabetically with optional MSV search"""
        try:
            query = {'is_placeholder': {'$ne': True}}
            
            # Add MSV search filter if provided
            if search_msv:
                query['msv'] = {'$regex': search_msv, '$options': 'i'}
            
            # Determine sort field and direction
            sort_field = 'name' if sort_by == 'name' else sort_by
            
            faces = self.faces_collection.find(query).sort(sort_field, 1)
            
            result = []
            for face in faces:
                result.append({
                    'id': str(face['_id']),
                    'name': face.get('name', ''),
                    'msv': face.get('msv', ''),
                    'class_name': face.get('class_name', ''),
                    'image_path': face.get('image_path', ''),
                    'created_at': face.get('created_at').isoformat() if face.get('created_at') else None
                })
            return result
        except Exception as e:
            print(f"Error getting all students: {e}")
            return []
    
    def get_faces_by_user(self, user_id):
        """Get all faces registered by a user"""

        return list(self.faces_collection.find({'user_id': ObjectId(user_id)}))
    
    def delete_face(self, face_id):
        """Delete a face entry"""

        result = self.faces_collection.delete_one({'_id': ObjectId(face_id)})
        return result.deleted_count > 0

    def get_faces_by_class(self, class_name):
        try:
            # Exclude placeholder entries
            faces = self.faces_collection.find({
                'class_name': class_name,
                'is_placeholder': {'$ne': True}
            })
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

    def get_face_by_id(self, face_id):
        """Get a single face by ID"""
        try:
            return self.faces_collection.find_one({'_id': ObjectId(face_id)})
        except Exception as e:
            print(f"Error getting face by id: {e}")
            return None

    def update_face(self, face_id, name, msv, encoding=None, image_path=None):
        """Update face info (name, msv, optionally encoding and image)"""
        try:
            # First check if the face exists
            existing = self.faces_collection.find_one({'_id': ObjectId(face_id)})
            if not existing:
                print(f"Face with id {face_id} not found")
                return False
            
            update_data = {
                'name': name,
                'msv': msv,
                'updated_at': datetime.utcnow()
            }
            if encoding is not None:
                update_data['encoding'] = encoding.tolist() if hasattr(encoding, 'tolist') else encoding
            if image_path is not None:
                update_data['image_path'] = image_path

            result = self.faces_collection.update_one(
                {'_id': ObjectId(face_id)},
                {'$set': update_data}
            )
            # Return True if document was found, regardless of whether data changed
            return result.matched_count > 0
        except Exception as e:
            print(f"Error updating face: {e}")
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

    def create_class(self, class_name, user_id):
        """Create a new empty class by adding a placeholder document"""
        try:
            # Create an empty placeholder in faces_collection
            # This will be replaced when actual students are added
            class_data = {
                'name': '__class_placeholder__',
                'msv': '__placeholder__',
                'class_name': class_name,
                'encoding': [],
                'image_path': '',
                'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
                'created_at': datetime.utcnow(),
                'is_placeholder': True
            }
            result = self.faces_collection.insert_one(class_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating class: {e}")
            return None

    def rename_class(self, old_name, new_name):
        """Rename a class - update all related collections"""
        try:
            faces_result = self.faces_collection.update_many(
                {'class_name': old_name},
                {'$set': {'class_name': new_name}}
            )
            attendance_result = self.attendance_collection.update_many(
                {'class_name': old_name},
                {'$set': {'class_name': new_name}}
            )
            sessions_result = self.attendance_sessions_collection.update_many(
                {'class_name': old_name},
                {'$set': {'class_name': new_name}}
            )
            schedules_result = self.schedules_collection.update_many(
                {'class_name': old_name},
                {'$set': {'class_name': new_name}}
            )
            return {
                'faces_updated': faces_result.modified_count,
                'attendance_updated': attendance_result.modified_count,
                'sessions_updated': sessions_result.modified_count,
                'schedules_updated': schedules_result.modified_count
            }
        except Exception as e:
            print(f"Error renaming class: {e}")
            return None
    
    # Attendance operations
    def create_attendance(self, name, class_name, user_id, attendance_type='in', attendance_time=None, allow_duplicate=False, face_image=None, msv=None):
        try:
            
            now = attendance_time or datetime.now()
            if not allow_duplicate:
                today_start = datetime(now.year, now.month, now.day)
                today_end = today_start + timedelta(days=1)
                
                # Use MSV for duplicate check if available, otherwise use name
                query = {
                    'class_name': class_name,
                    'attendance_type': attendance_type,
                    'timestamp': {
                        '$gte': today_start,
                        '$lt': today_end
                    }
                }
                if msv:
                    query['msv'] = msv
                else:
                    query['name'] = name
                
                existing = self.attendance_collection.find_one(query)
                
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
            if msv:
                attendance_data['msv'] = msv
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

            # Get attendance records with both msv and name fields
            present_records = list(self.attendance_collection.find(summary_query, {'name': 1, 'msv': 1}))
            present_msvs = set()
            for record in present_records:
                # First try to use MSV directly from attendance record
                msv = record.get('msv')
                if msv:
                    present_msvs.add(msv)
                else:
                    # Fallback: lookup MSV from faces collection by name
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

    def get_attendance_sessions_by_class(self, class_name, limit=50, start_date=None, end_date=None):
        try:
            # Build query with optional date filters
            query = {'class_name': class_name}
            
            # Filter by date range on end_time (the session completion time)
            if start_date or end_date:
                end_time_filter = {}
                if start_date:
                    end_time_filter['$gte'] = start_date
                if end_date:
                    end_time_filter['$lte'] = end_date
                if end_time_filter:
                    query['end_time'] = end_time_filter
            
            sessions = self.attendance_sessions_collection.find(
                query
            ).sort('end_time', -1).limit(limit)

            result = []
            for record in sessions:
                start_time = record.get('start_time')
                end_time = record.get('end_time')
                attendance_type = record.get('attendance_type')

                # Use MSV instead of name for unique identification
                student_msvs = set(self.get_class_students_msvs(class_name))
                total_students = len(student_msvs)

                present_faces = record.get('present_faces') or []
                if present_faces:
                    # Get MSVs from present_faces
                    present_msvs = {face.get('msv') for face in present_faces if face.get('msv')}
                else:
                    records_in_range = self.get_attendance_records_in_range(
                        class_name,
                        attendance_type,
                        start_time,
                        end_time
                    )
                    present_msvs = {r.get('msv') for r in records_in_range if r.get('msv')}

                present_count = len(present_msvs & student_msvs)
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

    def get_class_students_msvs(self, class_name):
        """Get all MSVs of students in a class"""
        try:
            return list(self.faces_collection.distinct('msv', {'class_name': class_name}))
        except Exception as e:
            print(f"Error getting class students MSVs: {e}")
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
                    'msv': record.get('msv'),
                    'face_image': record.get('face_image'),
                    'timestamp': record.get('timestamp').isoformat() if record.get('timestamp') else ''
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
    def create_schedule(self, class_name, attendance_type, rtsp_url, start_hour, start_minute, duration_minutes, user_id, send_telegram=False, end_hour=0, end_minute=0, selected_dates=None):
        """Create a new attendance schedule"""
        try:
            schedule_data = {
                'class_name': class_name,
                'attendance_type': attendance_type,
                'rtsp_url': rtsp_url,
                'start_hour': start_hour,
                'start_minute': start_minute,
                'end_hour': end_hour,
                'end_minute': end_minute,
                'duration_minutes': duration_minutes,
                'selected_dates': selected_dates or [],
                'completed_dates': [],
                'active': True,
                'send_telegram': send_telegram,
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
                    'end_hour': s.get('end_hour', 0),
                    'end_minute': s.get('end_minute', 0),
                    'duration_minutes': s.get('duration_minutes', 15),
                    'selected_dates': s.get('selected_dates', []),
                    'completed_dates': s.get('completed_dates', []),
                    'active': s.get('active', False),
                    'send_telegram': s.get('send_telegram', False),
                    'created_at': s.get('created_at').isoformat() if s.get('created_at') else None,
                    'last_run_date': str(s.get('last_run_date')) if s.get('last_run_date') else None
                })
            return result
        except Exception as e:
            print(f"Error getting schedules: {e}")
            return []

    def get_all_schedules(self):
        """Get all schedules across all classes"""
        try:
            schedules = self.schedules_collection.find().sort('created_at', -1)
            result = []
            for s in schedules:
                result.append({
                    'id': str(s['_id']),
                    'class_name': s.get('class_name'),
                    'attendance_type': s.get('attendance_type', 'in'),
                    'rtsp_url': s.get('rtsp_url', '0'),
                    'start_hour': s.get('start_hour', 0),
                    'start_minute': s.get('start_minute', 0),
                    'end_hour': s.get('end_hour', 0),
                    'end_minute': s.get('end_minute', 0),
                    'duration_minutes': s.get('duration_minutes', 15),
                    'selected_dates': s.get('selected_dates', []),
                    'completed_dates': s.get('completed_dates', []),
                    'active': s.get('active', False),
                    'send_telegram': s.get('send_telegram', False),
                    'created_at': s.get('created_at').isoformat() if s.get('created_at') else None,
                    'last_run_date': str(s.get('last_run_date')) if s.get('last_run_date') else None
                })
            return result
        except Exception as e:
            print(f"Error getting all schedules: {e}")
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
                    'end_hour': s.get('end_hour', 0),
                    'end_minute': s.get('end_minute', 0),
                    'duration_minutes': s.get('duration_minutes', 15),
                    'selected_dates': s.get('selected_dates', []),
                    'completed_dates': s.get('completed_dates', []),
                    'send_telegram': s.get('send_telegram', False),
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
            today_str = datetime.now().strftime('%Y-%m-%d')
            schedule = self.schedules_collection.find_one({'_id': ObjectId(schedule_id)})
            if not schedule:
                return False

            # Add today to completed_dates
            completed_dates = schedule.get('completed_dates', [])
            if today_str not in completed_dates:
                completed_dates.append(today_str)

            selected_dates = schedule.get('selected_dates', [])
            update_data = {
                'completed_dates': completed_dates,
                'last_run_date': datetime.now()
            }

            # Deactivate if all selected dates are completed
            if len(completed_dates) >= len(selected_dates) and len(selected_dates) > 0:
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

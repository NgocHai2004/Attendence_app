from datetime import datetime
from bson import ObjectId

class User:
    """User model for authentication"""
    
    # Role constants
    ROLE_USER = 'user'
    ROLE_ADMIN = 'admin'
    
    def __init__(self, username, email, password, role=None, _id=None, created_at=None, is_active=True):
        self._id = _id or ObjectId()
        self.username = username
        self.email = email
        self.password = password
        self.role = role or self.ROLE_USER
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self):
        """Convert user object to dictionary"""
        return {
            '_id': self._id,
            'username': self.username,
            'email': self.email,
            'password': self.password,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at
        }
    
    def is_admin(self):
        """Check if user has admin role"""
        return self.role == self.ROLE_ADMIN
    
    @staticmethod
    def from_dict(data):
        """Create user object from dictionary"""
        return User(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password'),
            role=data.get('role', User.ROLE_USER),
            _id=data.get('_id'),
            created_at=data.get('created_at'),
            is_active=data.get('is_active', True)
        )

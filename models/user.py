from datetime import datetime
from bson import ObjectId

class User:
    """User model for authentication"""
    
    def __init__(self, username, email, password, _id=None, created_at=None):
        self._id = _id or ObjectId()
        self.username = username
        self.email = email
        self.password = password
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self):
        """Convert user object to dictionary"""
        return {
            '_id': self._id,
            'username': self.username,
            'email': self.email,
            'password': self.password,
            'created_at': self.created_at
        }
    
    @staticmethod
    def from_dict(data):
        """Create user object from dictionary"""
        return User(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password'),
            _id=data.get('_id'),
            created_at=data.get('created_at')
        )

from datetime import datetime
from bson import ObjectId

class Face:
    """Face model for storing face encodings"""
    
    def __init__(self, name, encoding, image_path, user_id, class_name=None, _id=None, created_at=None):
        self._id = _id or ObjectId()
        self.name = name
        self.encoding = encoding  # 128-dimensional face encoding
        self.image_path = image_path
        self.user_id = user_id
        self.class_name = class_name
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self):
        """Convert face object to dictionary"""
        return {
            '_id': self._id,
            'name': self.name,
            'encoding': self.encoding,
            'image_path': self.image_path,
            'user_id': self.user_id,
            'class_name': self.class_name,
            'created_at': self.created_at
        }
    
    @staticmethod
    def from_dict(data):
        """Create face object from dictionary"""
        return Face(
            name=data.get('name'),
            encoding=data.get('encoding'),
            image_path=data.get('image_path'),
            user_id=data.get('user_id'),
            class_name=data.get('class_name'),
            _id=data.get('_id'),
            created_at=data.get('created_at')
        )

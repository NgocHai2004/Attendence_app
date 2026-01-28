import cv2
import numpy as np
from insightface.app import FaceAnalysis
from pathlib import Path

class FaceRecognitionService:
    """Service for face detection and recognition using existing models"""
    
    def __init__(self):
        self.app = None
        self.load_models()
    
    def load_models(self):
        try:
            model_root = Path('model_insight')
            self.app = FaceAnalysis(name='buffalo_l', root=str(model_root))
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            print("✓ InsightFace loaded successfully")
        except Exception as e:
            print(f"✗ Error loading InsightFace: {e}")
            self.app = None
    
    def detect_faces(self, image):
        """
        Detect faces in an image
        Returns: list of face bounding boxes [(x, y, w, h), ...]
        """
        try:
            if self.app is None:
                return self._detect_faces_opencv(image)
            
            faces = self.app.get(image)
            if not faces:
                return self._detect_faces_opencv(image)
            
            orig_h, orig_w = image.shape[:2]
            boxes = []
            for face in faces:
                x1, y1, x2, y2 = face.bbox.astype(int)
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(orig_w, x2)
                y2 = min(orig_h, y2)
                
                if x2 > x1 and y2 > y1:
                    boxes.append((x1, y1, x2 - x1, y2 - y1))
            
            return boxes if boxes else self._detect_faces_opencv(image)
        except Exception as e:
            print(f"Error in face detection: {e}")
            return self._detect_faces_opencv(image)
    
    def _detect_faces_opencv(self, image):
        """Fallback face detection using OpenCV Haar Cascade"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            return faces.tolist() if len(faces) > 0 else []
        except Exception as e:
            print(f"Error in OpenCV face detection: {e}")
            return []
    
    def extract_face_encoding(self, image, face_box):
        """
        Extract face encoding from a face region
        Returns: 512-dimensional face encoding vector
        """
        try:
            if self.app is None:
                print("Face encoder not loaded")
                return None
            
            faces = self.app.get(image)
            if not faces:
                return None
            
            if face_box is None:
                return faces[0].embedding
            
            x, y, w, h = face_box
            x1, y1, x2, y2 = x, y, x + w, y + h
            
            best_face = None
            best_iou = -1.0
            for face in faces:
                fx1, fy1, fx2, fy2 = face.bbox
                ix1 = max(x1, fx1)
                iy1 = max(y1, fy1)
                ix2 = min(x2, fx2)
                iy2 = min(y2, fy2)
                
                iw = max(0, ix2 - ix1)
                ih = max(0, iy2 - iy1)
                inter = iw * ih
                
                area_a = (x2 - x1) * (y2 - y1)
                area_b = max(0, (fx2 - fx1)) * max(0, (fy2 - fy1))
                union = area_a + area_b - inter
                
                iou = inter / union if union > 0 else 0
                if iou > best_iou:
                    best_iou = iou
                    best_face = face
            
            if best_face is None:
                return None
            
            return best_face.embedding
        except Exception as e:
            print(f"Error extracting face encoding: {e}")
            return None
    
    def compare_faces(self, encoding1, encoding2, threshold=0.4):
        """
        Compare two face encodings
        Returns: (is_match, distance)
        """
        try:
            enc1 = np.array(encoding1)
            enc2 = np.array(encoding2)
            enc1 = enc1 / (np.linalg.norm(enc1) + 1e-9)
            enc2 = enc2 / (np.linalg.norm(enc2) + 1e-9)
            
            similarity = float(np.dot(enc1, enc2))
            is_match = similarity > threshold
            
            return is_match, similarity
            
        except Exception as e:
            print(f"Error comparing faces: {e}")
            return False, float('inf')
    
    def identify_face(self, face_encoding, known_faces, threshold=0.4):
        """
        Identify a face from known faces
        Returns: (face_info, confidence) or (None, 0)
        """
        try:
            best_match = None
            best_similarity = float('-inf')
            
            for known_face in known_faces:
                is_match, similarity = self.compare_faces(
                    face_encoding, 
                    known_face['encoding'],
                    threshold
                )
                if is_match and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = known_face
            
            if best_match:
                confidence = max(0, min(100, best_similarity * 100))
                return best_match, confidence
            
            return None, 0
            
        except Exception as e:
            print(f"Error identifying face: {e}")
            return None, 0

# Global face recognition service instance
face_service = FaceRecognitionService()

import cv2
import numpy as np
import onnxruntime as ort
import tensorflow as tf
from pathlib import Path

class FaceRecognitionService:
    """Service for face detection and recognition using existing models"""
    
    def __init__(self):
        self.face_detector = None
        self.face_encoder = None
        self.load_models()
    
    def load_models(self):
        """Load face detection and recognition models"""
        try:
            # Load ONNX face detector
            detector_path = Path('facedet/facedet.onnx')
            if detector_path.exists():
                self.face_detector = ort.InferenceSession(str(detector_path))
                print("✓ Face detector loaded successfully")
            else:
                print(f"✗ Face detector not found at {detector_path}")
            
            # Load TFLite face encoder
            encoder_path = Path('facedet/facenet.tflite')
            if encoder_path.exists():
                self.face_encoder = tf.lite.Interpreter(model_path=str(encoder_path))
                self.face_encoder.allocate_tensors()
                print("✓ Face encoder loaded successfully")
            else:
                print(f"✗ Face encoder not found at {encoder_path}")
                
        except Exception as e:
            print(f"✗ Error loading models: {e}")
            raise
    
    def detect_faces(self, image):
        """
        Detect faces in an image
        Returns: list of face bounding boxes [(x, y, w, h), ...]
        """
        try:
            if self.face_detector is None:
                return self._detect_faces_opencv(image)

            # ===== ONNX INPUT INFO =====
            input_meta = self.face_detector.get_inputs()[0]
            input_name = input_meta.name
            _, c, input_h, input_w = input_meta.shape  # (1,3,640,640)

            orig_h, orig_w = image.shape[:2]

            # ===== PREPROCESS (BGR -> RGB, HWC -> CHW) =====
            img = cv2.resize(image, (input_w, input_h))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
            img = np.expand_dims(img, axis=0)   # Add batch

            # ===== INFERENCE =====
            outputs = self.face_detector.run(None, {input_name: img})

            faces = []

            # ===== PARSE OUTPUT (YOLO-style) =====
            detections = outputs[0]

            if detections.ndim == 3:
                detections = detections[0]  # batch size = 1

            for det in detections:
                if len(det) < 5:
                    continue

                conf = det[4]
                if conf < 0.5:
                    continue

                # Normalized coords → original image
                x1 = int(det[0] * orig_w)
                y1 = int(det[1] * orig_h)
                x2 = int(det[2] * orig_w)
                y2 = int(det[3] * orig_h)

                # Clamp
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(orig_w, x2)
                y2 = min(orig_h, y2)

                if x2 > x1 and y2 > y1:
                    faces.append((x1, y1, x2 - x1, y2 - y1))

            # Fallback nếu không detect được
            return faces if faces else self._detect_faces_opencv(image)

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
        Returns: 128-dimensional face encoding vector
        """
        try:
            if self.face_encoder is None:
                print("Face encoder not loaded")
                return None
            
            # Extract face region
            x, y, w, h = face_box
            face_img = image[y:y+h, x:x+w]
            
            # Preprocess for FaceNet
            face_resized = cv2.resize(face_img, (160, 160))
            face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)
            face_normalized = (face_rgb.astype(np.float32) - 127.5) / 128.0
            face_input = np.expand_dims(face_normalized, axis=0)
            
            # Get input and output details
            input_details = self.face_encoder.get_input_details()
            output_details = self.face_encoder.get_output_details()
            
            # Run inference
            self.face_encoder.set_tensor(input_details[0]['index'], face_input)
            self.face_encoder.invoke()
            encoding = self.face_encoder.get_tensor(output_details[0]['index'])
            
            return encoding[0]  # Return 128-dimensional vector
            
        except Exception as e:
            print(f"Error extracting face encoding: {e}")
            return None
    
    def compare_faces(self, encoding1, encoding2, threshold=0.3):
        """
        Compare two face encodings
        Returns: (is_match, distance)
        """
        try:
            # Convert to numpy arrays if needed
            enc1 = np.array(encoding1)
            enc2 = np.array(encoding2)
            
            # Calculate Euclidean distance
            distance = np.linalg.norm(enc1 - enc2)
            
            # Lower distance means more similar
            is_match = distance < threshold
            
            return is_match, distance
            
        except Exception as e:
            print(f"Error comparing faces: {e}")
            return False, float('inf')
    
    def identify_face(self, face_encoding, known_faces, threshold=0.3):
        """
        Identify a face from known faces
        Returns: (name, confidence) or (None, 0)
        """
        try:
            best_match = None
            best_distance = float('inf')
            
            for known_face in known_faces:
                is_match, distance = self.compare_faces(
                    face_encoding, 
                    known_face['encoding'],
                    threshold
                )
                
                if is_match and distance < best_distance:
                    best_distance = distance
                    best_match = known_face
            
            if best_match:
                # Convert distance to confidence (0-100%)
                confidence = max(0, min(100, (1 - best_distance) * 100))
                return best_match['name'], confidence
            
            return None, 0
            
        except Exception as e:
            print(f"Error identifying face: {e}")
            return None, 0

# Global face recognition service instance
face_service = FaceRecognitionService()

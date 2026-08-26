"""
Face Engine - InsightFace integration for face detection and recognition
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import logging

logger = logging.getLogger(__name__)

class FaceEngine:
    """Core face detection and recognition using InsightFace"""
    
    def __init__(self, model_name: str = "buffalo_l"):
        self.model_name = model_name
        self.app = None
        self._load_model()
    
    def _load_model(self):
        """Load InsightFace model"""
        try:
            from insightface.app import FaceAnalysis
            self.app = FaceAnalysis(
                name=self.model_name,
                providers=['CPUExecutionProvider']
            )
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info(f"Loaded InsightFace model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load InsightFace: {e}")
            raise
    
    def detect_faces(self, image: np.ndarray) -> List[Dict]:
        """
        Detect all faces in image
        Returns list of face dicts with bbox, embedding, confidence
        """
        if image is None or image.size == 0:
            return []
        
        try:
            faces = self.app.get(image)
            results = []
            
            for face in faces:
                bbox = face.bbox.astype(int).tolist()
                embedding = face.normed_embedding
                confidence = float(face.det_score)
                
                # Calculate face quality
                quality = self._assess_face_quality(image, bbox)
                
                results.append({
                    "bbox": bbox,
                    "embedding": embedding,
                    "confidence": confidence,
                    "quality": quality,
                    "size": (bbox[2] - bbox[0], bbox[3] - bbox[1])
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Face detection failed: {e}")
            return []
    
    def _assess_face_quality(self, image: np.ndarray, bbox: List[int]) -> float:
        """
        Assess face quality based on:
        - Face size relative to image
        - Blur level (Laplacian variance)
        - Brightness
        """
        x1, y1, x2, y2 = bbox
        face_region = image[y1:y2, x1:x2]
        
        if face_region.size == 0:
            return 0.0
        
        # Size score (larger faces are better)
        face_area = (x2 - x1) * (y2 - y1)
        img_area = image.shape[0] * image.shape[1]
        size_score = min(1.0, face_area / (img_area * 0.1))  # 10% of image is ideal
        
        # Blur score (Laplacian variance)
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY) if len(face_region.shape) == 3 else face_region
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_score = min(1.0, laplacian_var / 500)  # 500+ is sharp
        
        # Brightness score
        if len(face_region.shape) == 3:
            brightness = np.mean(cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY))
        else:
            brightness = np.mean(face_region)
        brightness_score = 1.0 - abs(brightness - 127.5) / 127.5  # Ideal is ~128
        
        # Weighted combination
        quality = (size_score * 0.4 + blur_score * 0.4 + brightness_score * 0.2)
        
        return float(quality)
    
    def get_best_face(self, image: np.ndarray) -> Optional[Dict]:
        """Get the best quality face from image"""
        faces = self.detect_faces(image)
        if not faces:
            return None
        
        # Return face with highest quality score
        return max(faces, key=lambda f: f["quality"])
    
    def compare_faces(
        self, 
        embedding1: np.ndarray, 
        embedding2: np.ndarray
    ) -> float:
        """
        Compare two face embeddings using cosine similarity
        Returns similarity score (0-1, higher = more similar)
        """
        # Normalize if not already normalized
        if np.linalg.norm(embedding1) < 0.9:
            embedding1 = embedding1 / np.linalg.norm(embedding1)
        if np.linalg.norm(embedding2) < 0.9:
            embedding2 = embedding2 / np.linalg.norm(embedding2)
        
        # Cosine similarity
        similarity = np.dot(embedding1, embedding2)
        
        return float(similarity)
    
    def compare_face_to_image(
        self,
        query_embedding: np.ndarray,
        target_image: np.ndarray,
        threshold: float = 0.5
    ) -> List[Dict]:
        """
        Compare query face embedding against all faces in target image
        Returns list of matches above threshold
        """
        target_faces = self.detect_faces(target_image)
        matches = []
        
        for face in target_faces:
            similarity = self.compare_faces(query_embedding, face["embedding"])
            if similarity >= threshold:
                matches.append({
                    "similarity": similarity,
                    "bbox": face["bbox"],
                    "quality": face["quality"],
                    "confidence": face["confidence"]
                })
        
        # Sort by similarity descending
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        
        return matches
    
    def crop_face(
        self, 
        image: np.ndarray, 
        bbox: List[int], 
        padding: float = 0.1
    ) -> np.ndarray:
        """Crop face region with padding"""
        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox
        
        # Add padding
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)
        
        return image[y1:y2, x1:x2]

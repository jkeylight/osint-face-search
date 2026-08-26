"""
Preprocessor - Multi-region face extraction and augmentation
"""
import cv2
import numpy as np
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

class FacePreprocessor:
    """Smart face preprocessing with multi-region extraction and augmentation"""
    
    def __init__(self, face_engine):
        self.face_engine = face_engine
    
    def extract_multi_region(
        self, 
        image: np.ndarray, 
        face: Dict
    ) -> Dict[str, np.ndarray]:
        """
        Extract multiple face regions for better search results
        
        Regions:
        - face_tight: Just the face (padding=0.1)
        - face_loose: Face + hair/neck (padding=0.5)
        - upper_body: Shoulders + face
        - full_head: Full head with context (padding=0.3)
        """
        bbox = face["bbox"]
        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox
        
        regions = {}
        
        # Tight face crop
        regions["face_tight"] = self._crop_with_padding(image, bbox, 0.1)
        
        # Loose face crop (includes hair/neck)
        regions["face_loose"] = self._crop_with_padding(image, bbox, 0.5)
        
        # Full head (includes more context)
        regions["full_head"] = self._crop_with_padding(image, bbox, 0.3)
        
        # Upper body (shoulders + face)
        face_height = y2 - y1
        upper_y1 = max(0, y1 - int(face_height * 0.5))
        upper_y2 = min(h, y2 + int(face_height * 0.3))
        regions["upper_body"] = image[upper_y1:upper_y2, max(0, x1 - int((x2-x1)*0.3)):min(w, x2 + int((x2-x1)*0.3))]
        
        return regions
    
    def _crop_with_padding(
        self, 
        image: np.ndarray, 
        bbox: List[int], 
        padding: float
    ) -> np.ndarray:
        """Crop region with padding"""
        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox
        
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)
        
        return image[y1:y2, x1:x2]
    
    def augment_image(self, image: np.ndarray) -> List[np.ndarray]:
        """
        Generate augmented versions for better search coverage
        - Brightness variations
        - Contrast enhancement
        - Grayscale
        """
        augmented = []
        
        # Brighter
        brighter = cv2.convertScaleAbs(image, alpha=1.2, beta=30)
        augmented.append(brighter)
        
        # Darker
        darker = cv2.convertScaleAbs(image, alpha=0.8, beta=-30)
        augmented.append(darker)
        
        # Higher contrast
        high_contrast = cv2.convertScaleAbs(image, alpha=1.5, beta=0)
        augmented.append(high_contrast)
        
        # Grayscale (convert back to 3 channels for consistency)
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray_3ch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            augmented.append(gray_3ch)
        
        return augmented
    
    def process_query(
        self, 
        image: np.ndarray
    ) -> Dict:
        """
        Full preprocessing pipeline for query image
        
        Returns:
        - best_face: Best quality face dict
        - regions: Multi-region crops
        - augmented: Augmented versions
        - embeddings: Embeddings for each region
        - quality_score: Overall quality score
        - threshold: Dynamic threshold based on quality
        """
        # Detect best face
        best_face = self.face_engine.get_best_face(image)
        
        if best_face is None:
            return {
                "best_face": None,
                "regions": {},
                "augmented": [],
                "embeddings": {},
                "quality_score": 0.0,
                "threshold": 0.5
            }
        
        # Extract multi-region crops
        regions = self.extract_multi_region(image, best_face)
        
        # Generate augmented versions (from loose crop)
        augmented = self.augment_image(regions.get("face_loose", regions["face_tight"]))
        
        # Generate embeddings for each region
        embeddings = {}
        for region_name, region_image in regions.items():
            if region_image.size > 0:
                faces = self.face_engine.detect_faces(region_image)
                if faces:
                    embeddings[region_name] = faces[0]["embedding"]
        
        # Calculate dynamic threshold based on quality
        quality_score = best_face["quality"]
        threshold = self._calculate_threshold(quality_score)
        
        return {
            "best_face": best_face,
            "regions": regions,
            "augmented": augmented,
            "embeddings": embeddings,
            "quality_score": quality_score,
            "threshold": threshold
        }
    
    def _calculate_threshold(self, quality_score: float) -> float:
        """
        Dynamic threshold based on query quality
        - High quality (>0.8): strict matching (0.75)
        - Medium quality (>0.6): standard matching (0.65)
        - Low quality (<=0.6): loose matching (0.50)
        """
        if quality_score > 0.8:
            return 0.75
        elif quality_score > 0.6:
            return 0.65
        else:
            return 0.50

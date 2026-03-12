"""Face recognition service using InsightFace - macOS desktop version."""

import logging
import os
import sys
from typing import Optional, List

import cv2
import numpy as np
from insightface.app import FaceAnalysis

try:
    import rawpy
    HAS_RAWPY = True
except ImportError:
    HAS_RAWPY = False

logger = logging.getLogger(__name__)

DETECTION_SIZE = (640, 640)
EMBEDDING_DIM = 512
MAX_IMAGE_DIM = 1280

RAW_EXTENSIONS = {
    ".arw", ".cr2", ".cr3", ".nef", ".nrw", ".orf", ".raf",
    ".rw2", ".pef", ".srw", ".dng", ".raw", ".3fr", ".erf",
}


def _imread_safe(path: str) -> Optional[np.ndarray]:
    """Read image with Unicode path support (Windows compatibility).
    Supports RAW camera files via rawpy if available.
    """
    ext = os.path.splitext(path)[1].lower()

    # RAW file: convert via rawpy
    if ext in RAW_EXTENSIONS and HAS_RAWPY:
        try:
            with rawpy.imread(path) as raw:
                rgb = raw.postprocess()
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.warning(f"RAW decode failed for {path}: {e}")
            return None

    # Standard image: read via OpenCV
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


class FaceService:
    """Singleton face recognition service."""

    _instance: Optional["FaceService"] = None
    _face_app: Optional[FaceAnalysis] = None
    _is_loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self, model_name: str = "buffalo_sc", on_progress=None) -> None:
        """Load InsightFace model. Can be called from a worker thread."""
        if self._is_loaded:
            return

        if on_progress:
            on_progress(f"Loading face recognition model ({model_name})...")

        # When bundled, use the root dir from INSIGHTFACE_HOME (set in main.py)
        root = os.environ.get("INSIGHTFACE_HOME", "~/.insightface")
        logger.info(f"Loading model from root: {root}")

        try:
            self._face_app = FaceAnalysis(
                name=model_name,
                root=root,
                providers=["CPUExecutionProvider"],
                allowed_modules=["detection", "recognition"],
            )
            self._face_app.prepare(ctx_id=0, det_size=DETECTION_SIZE)
            self._is_loaded = True
            logger.info("Face model loaded successfully")
        except Exception:
            self._face_app = None
            raise

    def _ensure_loaded(self) -> None:
        if not self._is_loaded:
            self.load_model()

    def detect_faces(self, image_path: str) -> List[dict]:
        """Detect all faces in an image.

        Returns:
            List of dicts with keys: bbox, embedding (np.ndarray 512-d), confidence
            bbox coordinates are in original image pixel space [x1, y1, x2, y2].
        """
        self._ensure_loaded()

        img = _imread_safe(str(image_path))
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        h, w = img.shape[:2]
        scale = 1.0
        if max(h, w) > MAX_IMAGE_DIM:
            scale = MAX_IMAGE_DIM / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        faces = self._face_app.get(img)

        results = []
        for face in faces:
            bbox = face.bbox.tolist()
            if scale != 1.0:
                inv = 1.0 / scale
                bbox = [v * inv for v in bbox]
            results.append({
                "bbox": bbox,
                "embedding": face.embedding,
                "confidence": float(face.det_score),
            })

        return results

    def get_best_embedding(self, image_path: str) -> np.ndarray:
        """Extract embedding for the single best face (highest confidence).

        Used for person registration. Raises ValueError if no faces found.
        """
        faces = self.detect_faces(image_path)
        if not faces:
            raise ValueError(f"No faces detected in: {image_path}")

        best = max(faces, key=lambda f: f["confidence"])
        return best["embedding"]


# Module-level singleton
face_service = FaceService()

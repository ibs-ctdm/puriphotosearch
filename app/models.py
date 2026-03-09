"""Data classes for application domain objects."""

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Person:
    id: int
    name: str
    photo_path: str
    embedding: np.ndarray
    thumbnail: Optional[bytes] = None
    created_at: str = ""


@dataclass
class EventFolder:
    id: int
    folder_path: str
    folder_name: str
    photo_count: int = 0
    face_count: int = 0
    is_processed: bool = False
    processed_at: Optional[str] = None


@dataclass
class Photo:
    id: int
    event_folder_id: int
    file_path: str
    filename: str
    file_size: int = 0
    width: int = 0
    height: int = 0
    face_count: int = 0
    is_processed: bool = False


@dataclass
class SearchMatch:
    photo_id: int
    file_path: str
    filename: str
    similarity: float
    face_id: int

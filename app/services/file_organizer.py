"""File organization: create person subfolders and copy matched photos."""

import logging
import os
import shutil
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class FileOrganizer:
    """Create named subfolders within event folders and copy matched photos."""

    @staticmethod
    def organize_single_person(
        event_folder_path: str,
        person_name: str,
        matched_photo_paths: List[str],
        on_progress: Optional[Callable] = None,
        is_cancelled: Optional[Callable] = None,
    ) -> dict:
        """Create a subfolder for one person and copy matched photos.

        Creates: <event_folder>/<person_name>/
        """
        safe_name = FileOrganizer._sanitize_folder_name(person_name)
        output_dir = os.path.join(event_folder_path, safe_name)
        os.makedirs(output_dir, exist_ok=True)

        copied = 0
        skipped = 0
        errors = 0
        total = len(matched_photo_paths)

        for i, src_path in enumerate(matched_photo_paths):
            if is_cancelled and is_cancelled():
                break

            filename = os.path.basename(src_path)
            dst_path = os.path.join(output_dir, filename)

            try:
                if os.path.exists(dst_path):
                    skipped += 1
                else:
                    shutil.copy2(src_path, dst_path)
                    copied += 1
            except Exception as e:
                logger.error(f"Failed to copy {src_path}: {e}")
                errors += 1

            if on_progress:
                on_progress(i + 1, total)

        return {
            "output_folder": output_dir,
            "copied": copied,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def organize_all_persons(
        event_folder_path: str,
        person_matches: Dict[str, List[str]],
        on_progress: Optional[Callable] = None,
        is_cancelled: Optional[Callable] = None,
    ) -> dict:
        """Create subfolders for all matched persons."""
        total_copied = 0
        details = []

        for person_name, photo_paths in person_matches.items():
            if is_cancelled and is_cancelled():
                break

            result = FileOrganizer.organize_single_person(
                event_folder_path=event_folder_path,
                person_name=person_name,
                matched_photo_paths=photo_paths,
                on_progress=lambda c, t: on_progress(person_name, c, t) if on_progress else None,
                is_cancelled=is_cancelled,
            )
            total_copied += result["copied"]
            details.append({"person_name": person_name, **result})

        return {
            "persons_organized": len(details),
            "total_copied": total_copied,
            "details": details,
        }

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        """Sanitize a name for use as a folder name on macOS."""
        invalid = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        result = name.strip()
        for ch in invalid:
            result = result.replace(ch, '_')
        while '__' in result:
            result = result.replace('__', '_')
        return result.strip('_') or "unnamed"

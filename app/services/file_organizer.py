"""File organization: create person subfolders and copy matched photos."""

import logging
import os
import shutil
from collections import defaultdict
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
        """Create person subfolders at each directory level that has matched photos.

        For each subdirectory containing matched photos, creates:
            <that_directory>/<person_name>/
        and copies the matched photos from that directory into it.
        """
        safe_name = FileOrganizer._sanitize_folder_name(person_name)

        # Group photos by their parent directory
        photos_by_dir: Dict[str, List[str]] = defaultdict(list)
        for path in matched_photo_paths:
            parent = os.path.dirname(path)
            photos_by_dir[parent].append(path)

        copied = 0
        skipped = 0
        errors = 0
        total = len(matched_photo_paths)
        output_folders = []
        progress_count = 0

        for parent_dir, photos in photos_by_dir.items():
            output_dir = os.path.join(parent_dir, safe_name)
            os.makedirs(output_dir, exist_ok=True)
            output_folders.append(output_dir)

            for src_path in photos:
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

                progress_count += 1
                if on_progress:
                    on_progress(progress_count, total)

        return {
            "output_folder": output_folders[0] if output_folders else event_folder_path,
            "output_folders": output_folders,
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

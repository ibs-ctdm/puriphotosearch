"""Workers for running face searches and organizing results."""

from app.workers.base_worker import BaseWorker
from app.services.search_service import SearchService
from app.services.file_organizer import FileOrganizer
from app.config import DB_PATH


class SearchSingleWorker(BaseWorker):
    """Search for one person in an event folder and organize results."""

    def __init__(self, person_dict, event_folder_id, event_folder_path, threshold, parent=None):
        super().__init__(parent)
        self.person = person_dict
        self.event_folder_id = event_folder_id
        self.event_folder_path = event_folder_path
        self.threshold = threshold

    def run(self):
        try:
            self.status_message.emit(f"Searching for {self.person['name']}...")

            matches = SearchService.search_person_in_event(
                db_path=DB_PATH,
                person_embeddings=self.person["embeddings"],
                event_folder_id=self.event_folder_id,
                threshold=self.threshold,
            )

            if not matches:
                self.finished_with_result.emit({
                    "person_name": self.person["name"],
                    "matches": [],
                    "organized": None,
                })
                return

            self.status_message.emit(
                f"Found {len(matches)} photos. Copying to subfolder..."
            )

            photo_paths = [m["file_path"] for m in matches]
            org_result = FileOrganizer.organize_single_person(
                event_folder_path=self.event_folder_path,
                person_name=self.person["name"],
                matched_photo_paths=photo_paths,
                on_progress=lambda c, t: self.progress.emit(c, t, "Copying photos..."),
                is_cancelled=self.is_cancelled,
            )

            self.finished_with_result.emit({
                "person_name": self.person["name"],
                "matches": matches,
                "organized": org_result,
            })

        except Exception as e:
            self.error.emit(str(e))


class SearchAllWorker(BaseWorker):
    """Search all persons against an event folder and organize results."""

    def __init__(self, persons, event_folder_id, event_folder_path, threshold, parent=None):
        super().__init__(parent)
        self.persons = persons
        self.event_folder_id = event_folder_id
        self.event_folder_path = event_folder_path
        self.threshold = threshold

    def run(self):
        try:
            self.status_message.emit("Searching all persons...")

            all_results = SearchService.search_all_persons_in_event(
                db_path=DB_PATH,
                persons=self.persons,
                event_folder_id=self.event_folder_id,
                threshold=self.threshold,
            )

            person_matches = {}
            for person_id, data in all_results.items():
                person_matches[data["name"]] = [m["file_path"] for m in data["matches"]]

            self.status_message.emit(
                f"Found matches for {len(person_matches)} persons. Organizing..."
            )

            org_result = FileOrganizer.organize_all_persons(
                event_folder_path=self.event_folder_path,
                person_matches=person_matches,
                on_progress=lambda name, c, t: self.progress.emit(
                    c, t, f"Copying photos for {name}..."
                ),
                is_cancelled=self.is_cancelled,
            )

            self.finished_with_result.emit({
                "search_results": all_results,
                "organized": org_result,
            })

        except Exception as e:
            self.error.emit(str(e))

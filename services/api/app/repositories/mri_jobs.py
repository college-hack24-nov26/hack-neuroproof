"""Protected filesystem persistence for Phase 2 MRI job metadata and artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from app.models.mri import MriJob
from cerebrachain_ml.architecture import MODALITY_ORDER


class MriJobRepositoryError(Exception):
    """A configured result-storage operation failed safely."""


class MriUploadError(MriJobRepositoryError):
    """An upload cannot be stored within configured safety constraints."""


class FileSystemMriJobRepository:
    """Persist non-identifying job metadata and derived files outside the repository."""

    _METADATA_FILENAME = "job.json"
    _SEGMENTATION_FILENAME = "segmentation.nii.gz"

    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise MriJobRepositoryError("Configured result storage must not be a symbolic link.")
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise MriJobRepositoryError("Configured result storage is unavailable.") from exc
        if not root.is_dir():
            raise MriJobRepositoryError("Configured result storage is not a directory.")
        self._root = root

    def create(self, job: MriJob) -> None:
        """Create an isolated directory and initial metadata for one job."""

        directory = self._job_directory(job.job_id)
        try:
            directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            (directory / "uploads").mkdir(mode=0o700)
            self.update(job)
        except FileExistsError as exc:
            raise MriJobRepositoryError("Could not reserve MRI result storage.") from exc
        except OSError as exc:
            raise MriJobRepositoryError("Could not create MRI result storage.") from exc

    def update(self, job: MriJob) -> None:
        """Atomically update repository-owned job metadata."""

        destination = self._job_directory(job.job_id) / self._METADATA_FILENAME
        self._atomic_json_write(destination, job.to_record())

    def get(self, job_id: str) -> MriJob:
        """Load one job after validating that its identifier cannot escape storage."""

        metadata_path = self._job_directory(job_id) / self._METADATA_FILENAME
        if not metadata_path.is_file() or metadata_path.is_symlink():
            raise MriJobRepositoryError("MRI segmentation job was not found.")
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Job metadata must be an object.")
            return MriJob.from_record(raw)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise MriJobRepositoryError("MRI segmentation job metadata is invalid.") from exc

    def save_upload(
        self,
        job_id: str,
        modality: str,
        source: BinaryIO,
        *,
        extension: str,
        max_bytes: int,
    ) -> Path:
        """Write one upload under a generated name with a strict byte limit."""

        if modality not in MODALITY_ORDER:
            raise MriUploadError("Unexpected MRI modality.")

        if extension not in {".nii", ".nii.gz"}:
            raise MriUploadError("Unsupported MRI file extension.")
        destination = self._job_directory(job_id) / "uploads" / f"{modality}{extension}"
        bytes_written = 0
        try:
            with destination.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise MriUploadError("MRI upload exceeds the configured size limit.")
                    target.write(chunk)
        except MriUploadError:
            destination.unlink(missing_ok=True)
            raise
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise MriUploadError("MRI upload could not be stored.") from exc

        if bytes_written == 0:
            destination.unlink(missing_ok=True)
            raise MriUploadError("MRI upload is empty.")
        return destination

    def modality_paths(self, job_id: str) -> dict[str, Path]:
        """Return generated upload paths in the established modality namespace."""

        directory = self._job_directory(job_id) / "uploads"
        paths: dict[str, Path] = {}
        for modality in MODALITY_ORDER:
            candidates = [directory / f"{modality}.nii.gz", directory / f"{modality}.nii"]
            path = next(
                (candidate for candidate in candidates if candidate.is_file() and not candidate.is_symlink()),
                None,
            )
            if path is None:
                raise MriJobRepositoryError("MRI upload is unavailable.")
            paths[modality] = path
        return paths

    def segmentation_path(self, job_id: str) -> Path:
        """Return the generated output location for a job's derived segmentation."""

        return self._job_directory(job_id) / self._SEGMENTATION_FILENAME

    def _job_directory(self, job_id: str) -> Path:
        try:
            normalized = str(UUID(job_id))
        except (ValueError, AttributeError) as exc:
            raise MriJobRepositoryError("MRI segmentation job was not found.") from exc
        return self._root / normalized

    @staticmethod
    def _atomic_json_write(destination: Path, content: dict[str, object]) -> None:
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                mode="w",
                encoding="utf-8",
                prefix=".job-",
                suffix=".json",
                delete=False,
            ) as temporary:
                json.dump(content, temporary, sort_keys=True, indent=2)
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)
        except OSError as exc:
            raise MriJobRepositoryError("MRI segmentation metadata could not be stored.") from exc

"""Protected, versioned persistence for newly aggregated coordinator checkpoints."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import torch


class CheckpointPersistenceError(RuntimeError):
    """A coordinator checkpoint could not be safely persisted."""


@dataclass(frozen=True)
class SavedCheckpoint:
    """Safe metadata for a checkpoint stored outside the repository."""

    storage_reference: str
    sha256: str
    size_bytes: int


class GlobalCheckpointManager:
    """Write only fresh outputs under a dedicated custom-coordinator namespace.

    This manager never reads, mutates, or derives a destination from the
    historical FedAvg A+B+C checkpoint.  A collision is treated as a failure,
    never as permission to overwrite a prior coordinator result.
    """

    namespace_name = "custom-coordinator"

    def __init__(self, storage_root: Path | None) -> None:
        self._storage_root = storage_root

    @property
    def is_configured(self) -> bool:
        return self._storage_root is not None

    def save(
        self,
        *,
        model_version_id: UUID,
        state_dict: Mapping[str, torch.Tensor],
        metadata: Mapping[str, object],
    ) -> SavedCheckpoint:
        """Persist a new checkpoint once using an atomic no-overwrite publish."""

        namespace = self._namespace()
        filename = f"{model_version_id}.pt"
        destination = namespace / filename
        if destination.exists() or destination.is_symlink():
            raise CheckpointPersistenceError("Coordinator checkpoint version already exists.")

        temporary_path: Path | None = None
        try:
            handle, temporary_name = tempfile.mkstemp(
                dir=namespace,
                prefix=".pending-",
                suffix=".pt",
            )
            temporary_path = Path(temporary_name)
            os.chmod(temporary_path, 0o600)
            with os.fdopen(handle, "wb") as output:
                torch.save({"state_dict": dict(state_dict), "metadata": dict(metadata)}, output)
                output.flush()
                os.fsync(output.fileno())

            # os.link publishes only if the target does not exist; unlike replace,
            # it cannot overwrite a previously recorded checkpoint.
            os.link(temporary_path, destination)
            temporary_path.unlink()
            temporary_path = None
            self._fsync_directory(namespace)
            return SavedCheckpoint(
                storage_reference=f"{self.namespace_name}/{filename}",
                sha256=self._sha256(destination),
                size_bytes=destination.stat().st_size,
            )
        except FileExistsError as exc:
            raise CheckpointPersistenceError("Coordinator checkpoint version already exists.") from exc
        except OSError as exc:
            raise CheckpointPersistenceError("Coordinator checkpoint could not be persisted.") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _namespace(self) -> Path:
        if self._storage_root is None:
            raise CheckpointPersistenceError("Federation checkpoint storage is not configured.")
        if self._storage_root.is_symlink() or not self._storage_root.is_dir():
            raise CheckpointPersistenceError("Federation checkpoint storage is unavailable.")
        namespace = self._storage_root / self.namespace_name
        if namespace.exists() and namespace.is_symlink():
            raise CheckpointPersistenceError("Federation checkpoint namespace is unsafe.")
        namespace.mkdir(mode=0o700, exist_ok=True)
        if not namespace.is_dir() or namespace.is_symlink():
            raise CheckpointPersistenceError("Federation checkpoint namespace is unavailable.")
        return namespace

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

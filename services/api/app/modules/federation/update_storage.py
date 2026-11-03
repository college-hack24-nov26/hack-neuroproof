"""Private, no-overwrite storage for bounded hospital update archives."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


class UpdateArtifactStorageError(RuntimeError):
    """A private model-update artifact could not be stored safely."""


@dataclass(frozen=True)
class StoredUpdateArtifact:
    """Logical reference and integrity metadata; never an absolute storage path."""

    storage_reference: str
    sha256: str
    size_bytes: int


class ModelUpdateArtifactStorage:
    """Write new update archives under a private dedicated namespace only."""

    namespace_name = "model-updates"
    proof_namespace_name = "model-update-proofs"

    def __init__(self, storage_root: Path | None) -> None:
        self._storage_root = storage_root

    @property
    def is_configured(self) -> bool:
        return self._is_private_root()

    def save(
        self,
        *,
        federation_round_id: UUID,
        submission_id: UUID,
        content: bytes,
    ) -> StoredUpdateArtifact:
        """Atomically publish an archive once without allowing replacement."""

        return self._save(
            namespace_name=self.namespace_name,
            federation_round_id=federation_round_id,
            submission_id=submission_id,
            suffix=".zip",
            content=content,
        )

    def save_proof(
        self,
        *,
        federation_round_id: UUID,
        submission_id: UUID,
        content: bytes,
    ) -> StoredUpdateArtifact:
        """Persist one public proof envelope privately without replacement."""

        return self._save(
            namespace_name=self.proof_namespace_name,
            federation_round_id=federation_round_id,
            submission_id=submission_id,
            suffix=".json",
            content=content,
        )

    def read_update(
        self,
        *,
        federation_round_id: UUID,
        submission_id: UUID,
        max_bytes: int,
    ) -> bytes:
        """Read the known server-created archive, never a client-provided path."""

        return self._read(
            namespace_name=self.namespace_name,
            federation_round_id=federation_round_id,
            submission_id=submission_id,
            suffix=".zip",
            max_bytes=max_bytes,
        )

    def _save(
        self,
        *,
        namespace_name: str,
        federation_round_id: UUID,
        submission_id: UUID,
        suffix: str,
        content: bytes,
    ) -> StoredUpdateArtifact:
        namespace = self._namespace(namespace_name, federation_round_id)
        filename = f"{submission_id}{suffix}"
        destination = namespace / filename
        if destination.exists() or destination.is_symlink():
            raise UpdateArtifactStorageError("Update artifact version already exists.")
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=namespace,
                prefix=".pending-",
                suffix=".zip",
            )
            temporary_path = Path(temporary_name)
            os.chmod(temporary_path, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary_path, destination)
            temporary_path.unlink()
            temporary_path = None
            self._fsync_directory(namespace)
            return StoredUpdateArtifact(
                storage_reference=f"{namespace_name}/{federation_round_id}/{filename}",
                sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        except FileExistsError as exc:
            raise UpdateArtifactStorageError("Update artifact version already exists.") from exc
        except OSError as exc:
            raise UpdateArtifactStorageError("Update artifact could not be persisted.") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _read(
        self,
        *,
        namespace_name: str,
        federation_round_id: UUID,
        submission_id: UUID,
        suffix: str,
        max_bytes: int,
    ) -> bytes:
        if max_bytes <= 0:
            raise UpdateArtifactStorageError("Update artifact size limit is invalid.")
        namespace = self._namespace(namespace_name, federation_round_id)
        destination = namespace / f"{submission_id}{suffix}"
        if destination.is_symlink() or not destination.is_file() or destination.stat().st_size > max_bytes:
            raise UpdateArtifactStorageError("Update artifact is unavailable.")
        try:
            content = destination.read_bytes()
        except OSError as exc:
            raise UpdateArtifactStorageError("Update artifact is unavailable.") from exc
        if len(content) > max_bytes:
            raise UpdateArtifactStorageError("Update artifact is unavailable.")
        return content

    def _namespace(self, namespace_name: str, federation_round_id: UUID) -> Path:
        if not self._is_private_root():
            raise UpdateArtifactStorageError("Federation update storage is unavailable.")
        assert self._storage_root is not None
        root = self._storage_root / namespace_name
        namespace = root / str(federation_round_id)
        for candidate in (root, namespace):
            if candidate.exists() and candidate.is_symlink():
                raise UpdateArtifactStorageError("Federation update storage namespace is unsafe.")
            candidate.mkdir(mode=0o700, exist_ok=True)
            if not candidate.is_dir() or candidate.is_symlink():
                raise UpdateArtifactStorageError("Federation update storage namespace is unavailable.")
        return namespace

    def _is_private_root(self) -> bool:
        """Require a pre-created non-symlink root inaccessible to other users."""

        if self._storage_root is None or self._storage_root.is_symlink() or not self._storage_root.is_dir():
            return False
        try:
            permissions = stat.S_IMODE(self._storage_root.stat().st_mode)
        except OSError:
            return False
        return permissions & 0o077 == 0

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

"""Fixtures for tests that explicitly opt into local external MRI assets."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import Settings
from cerebrachain_ml.architecture import MODALITY_ORDER


@pytest.fixture(scope="session")
def postgres_test_database_url() -> str:
    """Require an explicit, dedicated PostgreSQL test database; never use SQLite."""

    value = os.getenv("CEREBRACHAIN_TEST_DATABASE_URL")
    if not value:
        pytest.skip("CEREBRACHAIN_TEST_DATABASE_URL is not configured.")
    if not value.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("CEREBRACHAIN_TEST_DATABASE_URL must use PostgreSQL.")
    database_name = value.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0].lower()
    if "test" not in database_name:
        pytest.skip("CEREBRACHAIN_TEST_DATABASE_URL must target a dedicated test database.")
    return value


@pytest.fixture(scope="session")
def external_model_path() -> Path:
    """Require an explicit external checkpoint rather than embedding its path in tests."""

    value = os.getenv("CEREBRACHAIN_TEST_MODEL_CHECKPOINT")
    if not value:
        pytest.skip("CEREBRACHAIN_TEST_MODEL_CHECKPOINT is not configured.")
    path = Path(value)
    if not path.is_file():
        pytest.skip("Configured external model checkpoint is unavailable.")
    return path


@pytest.fixture(scope="session")
def external_model_sha256() -> str:
    """Read the expected public artifact hash from the test environment."""

    value = os.getenv("CEREBRACHAIN_TEST_MODEL_SHA256")
    if not value:
        pytest.skip("CEREBRACHAIN_TEST_MODEL_SHA256 is not configured.")
    return value


@pytest.fixture(scope="session")
def external_mri_case_dir() -> Path:
    """Require an explicit local research MRI case directory for integration tests."""

    value = os.getenv("CEREBRACHAIN_TEST_MRI_CASE_DIR")
    if not value:
        pytest.skip("CEREBRACHAIN_TEST_MRI_CASE_DIR is not configured.")
    path = Path(value)
    if not path.is_dir():
        pytest.skip("Configured local MRI case directory is unavailable.")
    return path


@pytest.fixture
def external_mri_paths(external_mri_case_dir: Path) -> dict[str, Path]:
    """Return explicit modality paths for the selected research case."""

    patient_id = external_mri_case_dir.name
    paths = {
        modality: external_mri_case_dir / f"{patient_id}_{modality}.nii.gz"
        for modality in MODALITY_ORDER
    }
    missing = [modality for modality, path in paths.items() if not path.is_file()]
    if missing:
        pytest.skip(f"Configured MRI case is missing modalities: {', '.join(missing)}")
    return paths


@pytest.fixture
def configured_settings(
    external_model_path: Path,
    external_model_sha256: str,
    tmp_path: Path,
) -> Settings:
    """Create per-test protected result storage under pytest's temporary root."""

    return Settings(
        model_checkpoint_path=external_model_path,
        model_sha256=external_model_sha256,
        result_storage_dir=tmp_path / "protected-results",
        inference_device="cpu",
        max_upload_bytes=64 * 1024 * 1024,
        cpu_threads=0,
        sliding_window_overlap=0.0,
    )

"""Regression coverage for real inference through the FedAvg model-selection path."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings
from app.services.mri_segmentation import MriSegmentationService
from app.services.mri_viewer import render_mri_slice


def test_global_fedavg_selection_runs_real_inference_and_records_provenance(
    configured_settings: Settings,
    external_model_path: Path,
    external_model_sha256: str,
    external_mri_paths: dict[str, Path],
) -> None:
    """The selected FedAvg checkpoint, not the local default, is used and recorded."""

    global_settings = replace(
        configured_settings,
        global_model_checkpoint_path=external_model_path,
        global_model_sha256=external_model_sha256,
    )
    service = MriSegmentationService(global_settings)
    with ExitStack() as stack:
        uploads = {
            modality: UploadFile(
                filename=path.name,
                file=stack.enter_context(path.open("rb")),
                headers={"content-type": "application/gzip"},
            )
            for modality, path in external_mri_paths.items()
        }
        submitted = service.submit(uploads, model_source="global_fedavg_abc")

    assert submitted.status.value == "completed"
    assert submitted.model_source == "global_fedavg_abc"
    assert submitted.model_sha256 == external_model_sha256

    result = service.get_completed_result(submitted.job_id)
    assert result.model_source == "global_fedavg_abc"
    assert result.model_sha256 == external_model_sha256
    assert result.statistics is not None

    modality_paths, segmentation_path = service.viewer_artifact_paths(
        submitted.job_id
    )
    preview = render_mri_slice(
        modality_paths["flair"],
        segmentation_path,
        plane="axial",
        position=0.5,
        overlay=True,
    )
    assert preview.startswith(b"\x89PNG\r\n\x1a\n")

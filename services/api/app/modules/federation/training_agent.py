"""Hospital-local MONAI training-agent preparation boundary.

This module validates authorized local inputs and approved checkpoint provenance.
It deliberately does not start a training loop unless a future deployment gives
both configuration and per-run authorization.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import torch

from app.core.config import Settings
from app.models.federation import FederationModelVersion, FederationTrainingAgent
from app.modules.federation.fedavg import state_dict_sha256
from app.modules.federation.update_archive import build_model_update_archive
from app.services.authentication import Principal
from cerebrachain_ml.architecture import MODALITY_ORDER
from cerebrachain_ml.checkpoint import load_verified_model
from cerebrachain_ml.errors import CheckpointIntegrityError, ModelLoadError, MriValidationError
from cerebrachain_ml.preprocessing import preprocess_mri


# This is an authorization catalogue, not a filesystem mapping. Dataset roots
# are supplied only on the relevant hospital-local agent deployment.
AUTHORIZED_CASE_BY_HOSPITAL_SLUG: dict[str, str | None] = {
    "hospital-a": "BraTS2021_00495",
    "hospital-b": "BraTS2021_00000",
    "hospital-c": "BraTS2021_00002",
    "hospital-d": "BraTS2021_00130",
    "hospital-e": None,
}


class TrainingAgentError(RuntimeError):
    """A training-agent action is unavailable or not authorized."""


@dataclass(frozen=True)
class DatasetAuthorization:
    """Server-safe dataset assignment information without a local path."""

    case_reference: str | None
    status: str


@dataclass(frozen=True)
class DatasetGeometryValidation:
    """Verified local geometry metadata with no MRI pixels or path disclosure."""

    case_reference: str
    modality_order: tuple[str, str, str, str]
    input_shape: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class TrainingPreparation:
    """A loaded approved base model and its auditable provenance."""

    model: torch.nn.Module
    checkpoint_sha256: str
    checkpoint_size_bytes: int
    model_version_commitment: str
    dataset_geometry: DatasetGeometryValidation
    configuration: "LocalTrainingConfiguration"


@dataclass(frozen=True)
class LocalTrainingConfiguration:
    """Explicit future-run configuration; constructing it does not start training."""

    local_epochs: int
    batch_size: int
    learning_rate: float

    def __post_init__(self) -> None:
        if self.local_epochs <= 0 or self.batch_size <= 0 or self.learning_rate <= 0:
            raise TrainingAgentError("Local training configuration values must be positive.")


def dataset_authorization_for_hospital(hospital_slug: str) -> DatasetAuthorization:
    """Return the explicit known assignment, or a safe no-dataset default."""

    case_reference = AUTHORIZED_CASE_BY_HOSPITAL_SLUG.get(hospital_slug)
    if case_reference is None:
        return DatasetAuthorization(case_reference=None, status="not_approved")
    return DatasetAuthorization(
        case_reference=case_reference,
        status="authorized_unvalidated",
    )


class HospitalTrainingAgent:
    """Prepare only the authenticated hospital's local training inputs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def validate_local_dataset(
        self,
        *,
        principal: Principal,
        agent: FederationTrainingAgent,
    ) -> DatasetGeometryValidation:
        """Load exactly four authorized local NIfTI files and validate geometry.

        This is an explicit agent call, never a dashboard side effect. It does
        not train, save a model, or upload MRI data.
        """

        case_reference = self._authorize_agent(principal, agent)
        root = self._settings.training_dataset_root
        if root is None or root.is_symlink() or not root.is_dir():
            raise TrainingAgentError("Authorized local training dataset is not configured.")
        case_directory = root / case_reference
        if case_directory.is_symlink() or not case_directory.is_dir():
            raise TrainingAgentError("Authorized local training dataset is unavailable.")
        paths = {
            modality: case_directory / f"{case_reference}_{modality}.nii.gz"
            for modality in MODALITY_ORDER
        }
        if any(path.is_symlink() or not path.is_file() for path in paths.values()):
            raise TrainingAgentError("Authorized local training dataset is incomplete.")
        try:
            prepared = preprocess_mri(paths)
        except MriValidationError as exc:
            raise TrainingAgentError("Authorized local MRI geometry validation failed.") from exc
        return DatasetGeometryValidation(
            case_reference=case_reference,
            modality_order=MODALITY_ORDER,
            input_shape=tuple(int(value) for value in prepared.input_tensor.shape),
        )

    def prepare_training(
        self,
        *,
        principal: Principal,
        agent: FederationTrainingAgent,
        model_version: FederationModelVersion,
        configuration: LocalTrainingConfiguration,
    ) -> TrainingPreparation:
        """Strict-load the configured approved 3D U-Net without training it."""

        # Ensure the no-training preparation path checks the required local
        # FLAIR/T1/T1CE/T2 geometry before it ever loads a base checkpoint.
        geometry = self.validate_local_dataset(principal=principal, agent=agent)
        if self._settings.model_checkpoint_path is None or self._settings.model_sha256 is None:
            raise TrainingAgentError("Approved local training checkpoint is not configured.")
        try:
            loaded = load_verified_model(
                self._settings.model_checkpoint_path,
                self._settings.model_sha256,
                device=self._settings.inference_device,
            )
        except (CheckpointIntegrityError, ModelLoadError) as exc:
            raise TrainingAgentError("Approved local training checkpoint could not be verified.") from exc
        state = OrderedDict(
            (name, tensor.detach().to(device="cpu"))
            for name, tensor in loaded.model.state_dict().items()
        )
        commitment = state_dict_sha256(state)
        if commitment != model_version.model_commitment:
            raise TrainingAgentError("Approved checkpoint does not match the selected model version.")
        return TrainingPreparation(
            model=loaded.model,
            checkpoint_sha256=loaded.checkpoint.sha256,
            checkpoint_size_bytes=loaded.checkpoint.size_bytes,
            model_version_commitment=commitment,
            dataset_geometry=geometry,
            configuration=configuration,
        )

    def build_authorized_update_archive(
        self,
        *,
        principal: Principal,
        agent: FederationTrainingAgent,
        preparation: TrainingPreparation,
        trained_state_dict: Mapping[str, torch.Tensor],
        sample_count: int,
        training_metadata: Mapping[str, object],
        execution_authorized: bool,
        proof_artifact_reference: str | None = None,
    ) -> bytes:
        """Serialize a completed authorized run; never starts training itself."""

        self._authorize_agent(principal, agent)
        if not self._settings.training_execution_enabled or not execution_authorized:
            raise TrainingAgentError("Local training execution is disabled pending explicit authorization.")
        metadata = dict(training_metadata)
        recorded_checkpoint_sha = metadata.get("base_checkpoint_sha256")
        if recorded_checkpoint_sha not in {None, preparation.checkpoint_sha256}:
            raise TrainingAgentError("Training metadata does not match the prepared checkpoint.")
        metadata["base_checkpoint_sha256"] = preparation.checkpoint_sha256
        return build_model_update_archive(
            state_dict=trained_state_dict,
            model_version_commitment=preparation.model_version_commitment,
            sample_count=sample_count,
            training_metadata=metadata,
            proof_artifact_reference=proof_artifact_reference,
        )

    @staticmethod
    def _authorize_agent(principal: Principal, agent: FederationTrainingAgent) -> str:
        if agent.hospital_id != principal.hospital_id or agent.status != "enrolled":
            raise TrainingAgentError("Training agent is not available for the authenticated hospital.")
        authorization = dataset_authorization_for_hospital(principal.hospital_slug)
        if authorization.case_reference is None or agent.authorized_case_reference != authorization.case_reference:
            raise TrainingAgentError("No approved local MRI training dataset is available for this hospital.")
        return authorization.case_reference

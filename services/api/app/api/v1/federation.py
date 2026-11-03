"""Authenticated custom-coordinator status and control-plane APIs.

The active coordinator has no Flower dependency. Legacy Flower experiments are
exposed only as read-only, explicitly historical evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import (
    get_database_session,
    get_settings,
    require_federation_operator,
    require_hospital_admin,
)
from app.core.config import Settings
from app.models.federation import (
    FederationGlobalCheckpoint,
    FederationModelVersion,
    FederationRound,
    FederationRoundParticipant,
    FederationTrainingAgent,
    FederationTrainingNode,
    FederationUpdateArtifact,
)
from app.modules.federation.checkpoints import GlobalCheckpointManager
from app.modules.federation.coordinator import (
    FederationCoordinator,
    HospitalNodeRegistry,
    ModelUpdateValidator,
)
from app.modules.federation.groth16 import verifier_from_settings
from app.modules.federation.training_agent import dataset_authorization_for_hospital
from app.modules.federation.update_storage import ModelUpdateArtifactStorage
from app.modules.federation.update_transport import (
    ModelUpdateSubmissionService,
    TrainingAgentRegistry,
)
from app.modules.federation.verification import Groth16ChunkProof, Groth16ProofEnvelope
from app.repositories.auth import AuthRepository
from app.repositories.federation import SqlAlchemyFederationRepository
from app.schemas.federation import (
    CoordinatorHospitalResponse,
    CoordinatorReadinessResponse,
    GlobalCheckpointResponse,
    Groth16ProofSubmissionRequest,
    ModelVersionCreateRequest,
    ModelVersionResponse,
    TrainingAgentEnrollmentRequest,
    TrainingAgentResponse,
    TrainingNodeEnrollmentRequest,
    TrainingNodeEnrollmentResponse,
    TrainingRoundCreateRequest,
    TrainingRoundParticipantResponse,
    TrainingRoundResponse,
    UpdateArtifactResponse,
    UpdatePreparationRequest,
)
from app.services.authentication import Principal

router = APIRouter(prefix="/federation", tags=["Federation"])

HISTORICAL_EXPERIMENTS = (
    (
        "fedavg_ab",
        "Historical Flower FedAvg Round 1 — A+B",
        "fedavg_round1_AB",
        "aggregation_metadata.json",
    ),
    (
        "fedavg_abc",
        "Historical Flower FedAvg Round 1 — A+B+C",
        "fedavg_round1_ABC",
        "aggregation_metadata.json",
    ),
    (
        "secure_abc",
        "Historical Flower Secure-Aggregation Smoke Test — A+B+C",
        "secagg_quantized_round1_ABC",
        "security_metrics.json",
    ),
)


def read_json(path: Path) -> dict:
    """Read only fixed small legacy evidence documents without mutating them."""

    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 256_000:
            return {}
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def file_sha256(path: Path) -> str | None:
    """Compute a historical checkpoint integrity hash without loading it."""

    try:
        if not path.is_file() or path.is_symlink():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def checkpoint_evidence(root: Path, experiment_dir: str, metadata: dict) -> dict:
    """Report historical checkpoint metadata without treating it as coordinator output."""

    path = root / experiment_dir / "global_model.pth"
    computed = file_sha256(path)
    expected = metadata.get("global_model_sha256") or metadata.get("global_model_sha")
    if computed is None:
        integrity = "unavailable"
    elif isinstance(expected, str):
        integrity = "matches_metadata" if computed.lower() == expected.lower().removeprefix("0x") else "mismatch"
    else:
        integrity = "sha256_computed_only"
    return {
        "sha256": computed,
        "integrity": integrity,
        "size_bytes": path.stat().st_size if computed is not None else None,
    }


def experiment_summary(root: Path, definition: tuple[str, str, str, str]) -> dict:
    """Build an explicitly historical Flower experiment summary from read-only files."""

    identifier, title, folder, filename = definition
    metadata = read_json(root / folder / filename)
    participants = metadata.get("participants", [])
    if not isinstance(participants, list):
        participants = []
    return {
        "id": identifier,
        "title": title,
        "metadata_available": bool(metadata),
        "round": metadata.get("round"),
        "participants": [value for value in participants if isinstance(value, str) and len(value) <= 64],
        "total_samples": metadata.get("total_samples"),
        "aggregation": metadata.get("aggregation"),
        "changed_global_parameters": metadata.get("changed_global_parameters"),
        "global_update_l2_norm": metadata.get("global_update_l2_norm"),
        "secure_aggregation": metadata.get("secure_aggregation", False),
        "distributed_privacy_verified": metadata.get("distributed_privacy_verified", False),
        "zk_proof_generated": metadata.get("zk_proof_generated", False),
        "blockchain_committed": metadata.get("blockchain_committed", False),
        "clinical_validation": metadata.get("clinical_validation", False),
        "single_process_smoke_test": metadata.get("single_process_smoke_test", False),
        "secure_sum_mismatches": metadata.get("secure_sum_mismatches"),
        "checkpoint": checkpoint_evidence(root, folder, metadata),
    }


def historical_evidence_summary() -> dict:
    """Return legacy evidence when configured; availability never blocks the coordinator."""

    configured_path = os.environ.get("CEREBRACHAIN_FEDERATION_EVIDENCE_DIR")
    if not configured_path:
        return {
            "source": "legacy_flower_read_only",
            "available": False,
            "experiments": [],
            "protocol_test": None,
        }
    root = Path(configured_path)
    if root.is_symlink() or not root.is_dir():
        return {
            "source": "legacy_flower_read_only",
            "available": False,
            "experiments": [],
            "protocol_test": None,
        }
    round6 = read_json(root / "live_round6_single_chunk" / "round_manifest.json")
    return {
        "source": "legacy_flower_read_only",
        "available": True,
        "experiments": [experiment_summary(root, definition) for definition in HISTORICAL_EXPERIMENTS],
        "protocol_test": {
            "round_label": round6.get("round"),
            "purpose": round6.get("purpose"),
            "full_model_proven": round6.get("fullModelProven", False),
            "live_proof_submitted": round6.get("liveProofSubmitted", False),
            "blockchain_verification_completed": round6.get("blockchainVerificationCompleted", False),
        },
    }


def node_response(node: FederationTrainingNode) -> TrainingNodeEnrollmentResponse:
    return TrainingNodeEnrollmentResponse(
        id=node.id,
        hospital_id=node.hospital_id,
        node_identifier=node.node_identifier,
        status=node.status,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def model_response(model: FederationModelVersion) -> ModelVersionResponse:
    return ModelVersionResponse(
        id=model.id,
        label=model.label,
        model_commitment=model.model_commitment,
        parent_model_version_id=model.parent_model_version_id,
        artifact_reference=model.artifact_reference,
        artifact_sha256=model.artifact_sha256,
        parameter_schema_commitment=model.parameter_schema_commitment,
        parameter_schema_available=model.parameter_schema is not None,
        created_at=model.created_at,
    )


def training_agent_response(agent: FederationTrainingAgent) -> TrainingAgentResponse:
    """Serialize training-agent metadata without local path or MRI disclosure."""

    return TrainingAgentResponse(
        id=agent.id,
        hospital_id=agent.hospital_id,
        training_node_id=agent.training_node_id,
        agent_identifier=agent.agent_identifier,
        status=agent.status,
        authorized_case_reference=agent.authorized_case_reference,
        dataset_status=agent.dataset_status,
        training_execution_enabled=agent.training_execution_enabled,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def update_artifact_response(artifact: FederationUpdateArtifact) -> UpdateArtifactResponse:
    """Serialize update provenance without archive contents or storage paths."""

    return UpdateArtifactResponse(
        id=artifact.id,
        federation_round_id=artifact.federation_round_id,
        hospital_id=artifact.hospital_id,
        training_node_id=artifact.training_node_id,
        training_agent_id=artifact.training_agent_id,
        model_version_id=artifact.model_version_id,
        status=artifact.status,
        artifact_sha256=artifact.artifact_sha256,
        artifact_size_bytes=artifact.artifact_size_bytes,
        update_commitment=artifact.update_commitment,
        parameter_schema_commitment=artifact.parameter_schema_commitment,
        sample_count=artifact.sample_count,
        proof_artifact_reference=artifact.proof_artifact_reference,
        proof_artifact_sha256=artifact.proof_artifact_sha256,
        proof_verification_status=artifact.proof_verification_status,
        training_metadata_recorded=artifact.training_metadata is not None,
        aggregation_eligible=bool(artifact.aggregation_eligible),
        proof_lifecycle=_proof_lifecycle(artifact),
        zk_circuit_version=artifact.zk_circuit_version,
        zk_verification_key_id=artifact.zk_verification_key_id,
        zk_coverage_complete=bool(artifact.zk_coverage_complete),
        rejection_code=artifact.rejection_code,
        rejection_reason=artifact.rejection_reason,
        prepared_at=artifact.prepared_at,
        submitted_at=artifact.submitted_at,
    )


def _proof_lifecycle(artifact: FederationUpdateArtifact) -> str:
    """Expose a truthful UI state without inferring verification from hashes."""

    if artifact.status == "rejected":
        return "rejected"
    if artifact.proof_verification_status == "verified":
        return "cryptographically_verified"
    if artifact.proof_verification_status == "pending_verification":
        return "verification_pending"
    if artifact.status == "submitted":
        return "awaiting_proof"
    return "prepared"


def participant_response(participant: FederationRoundParticipant) -> TrainingRoundParticipantResponse:
    return TrainingRoundParticipantResponse(
        hospital_id=participant.hospital_id,
        status=participant.status,
        sample_count=participant.sample_count,
        update_commitment=participant.update_commitment,
        proof_artifact_reference=participant.proof_artifact_reference,
        proof_verification_status=participant.proof_verification_status,
        verification_reason=participant.verification_reason,
        submitted_at=participant.submitted_at,
    )


def round_response(
    federation_round: FederationRound,
    participants: list[FederationRoundParticipant],
) -> TrainingRoundResponse:
    return TrainingRoundResponse(
        id=federation_round.id,
        base_model_version_id=federation_round.base_model_version_id,
        global_model_version_id=federation_round.global_model_version_id,
        status=federation_round.status,
        requires_zk_verification=federation_round.requires_zk_verification,
        research_mode=federation_round.research_mode,
        failure_reason=federation_round.failure_reason,
        created_at=federation_round.created_at,
        updated_at=federation_round.updated_at,
        completed_at=federation_round.completed_at,
        participants=[participant_response(item) for item in participants],
    )


def checkpoint_response(checkpoint: FederationGlobalCheckpoint) -> GlobalCheckpointResponse:
    return GlobalCheckpointResponse(
        federation_round_id=checkpoint.federation_round_id,
        model_version_id=checkpoint.model_version_id,
        storage_reference=checkpoint.storage_reference,
        checkpoint_sha256=checkpoint.checkpoint_sha256,
        size_bytes=checkpoint.size_bytes,
        aggregation_algorithm=checkpoint.aggregation_algorithm,
        participant_count=checkpoint.participant_count,
        total_sample_count=checkpoint.total_sample_count,
        created_at=checkpoint.created_at,
    )


@router.get("/summary")
def federation_summary(
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return active custom-coordinator state plus isolated historical evidence."""

    if principal.hospital_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital identity is required.",
        )

    repository = SqlAlchemyFederationRepository(session)
    is_operator = principal.email.lower() in settings.federation_operator_emails
    groth16_verifier = verifier_from_settings(settings)
    groth16_status = (
        "production_ready"
        if groth16_verifier.is_ready
        else "development_only"
        if groth16_verifier.is_available
        else "unavailable"
    )
    registry = HospitalNodeRegistry(repository)
    auth_repository = AuthRepository(session)

    hospital_records = (
        auth_repository.list_hospitals()
        if is_operator
        else [auth_repository.hospital_by_id(principal.hospital_id)]
    )

    hospitals = registry.dashboard_hospitals(
        [hospital for hospital in hospital_records if hospital is not None]
    )

    agents_by_hospital = {
        agent.hospital_id: agent
        for agent in repository.list_training_agents()
        if is_operator or agent.hospital_id == principal.hospital_id
    }

    rounds = repository.list_rounds() if is_operator else []
    round_items = [
        round_response(item, repository.participants_for_round(item.id)).model_dump(mode="json")
        for item in rounds
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coordinator": {
            "readiness": CoordinatorReadinessResponse(
                database_backed=True,
                checkpoint_storage_configured=settings.federation_checkpoint_storage_is_configured,
                update_storage_configured=ModelUpdateArtifactStorage(
                    settings.federation_update_storage_dir
                ).is_configured,
                groth16_verifier=groth16_status,
                production_aggregation="blocked_pending_groth16_verifier",
            ).model_dump(),
            "hospitals": [
                _coordinator_hospital_response(
                    item,
                    agents_by_hospital.get(item.hospital.id),
                ).model_dump()
                for item in hospitals
            ],
            "rounds": round_items,
            "models": [
                model_response(model).model_dump(mode="json")
                for model in (
                    repository.list_model_versions() if is_operator else []
                )
            ],
            "global_checkpoints": [
                checkpoint_response(checkpoint).model_dump(mode="json")
                for checkpoint in (
                    repository.list_checkpoints() if is_operator else []
                )
            ],
            "training_agents": [
                training_agent_response(agent).model_dump(mode="json")
                for agent in agents_by_hospital.values()
            ],
            "submitted_updates": [
                update_artifact_response(artifact).model_dump(mode="json")
                for artifact in repository.list_update_artifacts(
                    hospital_id=None if is_operator else principal.hospital_id
                )
            ],
        },
        "historical_evidence": (
            historical_evidence_summary()
            if is_operator
            else {
                "source": "legacy_flower_read_only",
                "available": False,
                "experiments": [],
                "protocol_test": None,
            }
        ),
        "disclaimer": (
            "Custom coordinator status records metadata only. A SHA-256 commitment is not a Groth16 proof. "
            "Production aggregation is fail-closed until a reviewed Groth16 verifier is configured. "
            "Historical Flower evidence remains read-only and is not custom-coordinator activity."
        ),
    }


def _coordinator_hospital_response(
    item,
    agent: FederationTrainingAgent | None,
) -> CoordinatorHospitalResponse:
    """Build status from metadata; never access a hospital-local dataset here."""

    assignment = dataset_authorization_for_hospital(item.hospital.slug)
    agent_status = agent.status if agent is not None else "not_enrolled"
    dataset_status = agent.dataset_status if agent is not None else assignment.status
    if item.training_node_status != "enrolled":
        readiness = "not_ready_missing_node"
    elif agent is None or agent_status != "enrolled":
        readiness = "not_ready_missing_agent"
    elif dataset_status == "not_approved":
        readiness = "not_ready_no_dataset"
    elif dataset_status != "geometry_validated":
        readiness = "not_ready_dataset_unvalidated"
    elif not agent.training_execution_enabled:
        readiness = "execution_disabled"
    else:
        readiness = "execution_authorization_required"
    return CoordinatorHospitalResponse(
        hospital_name=item.hospital.name,
        hospital_slug=item.hospital.slug,
        training_node_status=item.training_node_status,
        training_agent_status=agent_status,
        dataset_availability=dataset_status,
        training_readiness=readiness,
    )


@router.post(
    "/training-nodes/enroll",
    response_model=TrainingNodeEnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_training_node(
    request: TrainingNodeEnrollmentRequest,
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
) -> TrainingNodeEnrollmentResponse:
    """Explicitly enroll a node for the authenticated hospital only."""

    node = HospitalNodeRegistry(SqlAlchemyFederationRepository(session)).enroll_current_hospital(
        principal=principal,
        node_identifier=request.node_identifier,
    )
    return node_response(node)


@router.post(
    "/training-agents/enroll",
    response_model=TrainingAgentResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_training_agent(
    request: TrainingAgentEnrollmentRequest,
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> TrainingAgentResponse:
    """Enroll a hospital-local agent only after its node was explicitly enrolled."""

    agent = TrainingAgentRegistry(
        SqlAlchemyFederationRepository(session),
        execution_enabled=settings.training_execution_enabled,
    ).enroll_current_hospital(
        principal=principal,
        agent_identifier=request.agent_identifier,
    )
    return training_agent_response(agent)


@router.get("/models", response_model=list[ModelVersionResponse])
def list_model_versions(
    _: Principal = Depends(require_federation_operator),
    session: Session = Depends(get_database_session),
) -> list[ModelVersionResponse]:
    """List custom-coordinator model metadata, never checkpoint contents."""

    repository = SqlAlchemyFederationRepository(session)
    return [model_response(model) for model in repository.list_model_versions()]


@router.post(
    "/models",
    response_model=ModelVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_model_version(
    request: ModelVersionCreateRequest,
    principal: Principal = Depends(require_federation_operator),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> ModelVersionResponse:
    """Register base-model commitment metadata through an allowlisted operator."""

    coordinator = FederationCoordinator(
        SqlAlchemyFederationRepository(session),
        checkpoint_manager=GlobalCheckpointManager(settings.federation_checkpoint_dir),
    )
    model = coordinator.register_model_version(
        label=request.label,
        model_commitment=request.model_commitment.lower(),
        artifact_reference=request.artifact_reference,
        parameter_schema=(
            [item.model_dump() for item in request.parameter_schema]
            if request.parameter_schema is not None
            else None
        ),
        created_by_user_id=principal.user_id,
    )
    return model_response(model)


@router.get("/rounds", response_model=list[TrainingRoundResponse])
def list_training_rounds(
    _: Principal = Depends(require_federation_operator),
    session: Session = Depends(get_database_session),
) -> list[TrainingRoundResponse]:
    """List recent custom-coordinator round metadata and proof statuses."""

    repository = SqlAlchemyFederationRepository(session)
    return [
        round_response(item, repository.participants_for_round(item.id))
        for item in repository.list_rounds()
    ]


@router.post(
    "/rounds",
    response_model=TrainingRoundResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_training_round(
    request: TrainingRoundCreateRequest,
    principal: Principal = Depends(require_federation_operator),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> TrainingRoundResponse:
    """Create a draft round from explicit enrolled nodes; it does not train."""

    repository = SqlAlchemyFederationRepository(session)
    federation_round = FederationCoordinator(
        repository,
        checkpoint_manager=GlobalCheckpointManager(settings.federation_checkpoint_dir),
    ).create_round(
        base_model_version_id=request.base_model_version_id,
        participant_hospital_ids=request.participant_hospital_ids,
        created_by_user_id=principal.user_id,
        requires_zk_verification=request.requires_zk_verification,
        research_mode=request.research_mode,
    )
    return round_response(federation_round, repository.participants_for_round(federation_round.id))


@router.post("/rounds/{round_id}/open", response_model=TrainingRoundResponse)
def open_training_round(
    round_id: UUID,
    _: Principal = Depends(require_federation_operator),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> TrainingRoundResponse:
    """Open a draft round; raw private update transport remains a later phase."""

    repository = SqlAlchemyFederationRepository(session)
    federation_round = FederationCoordinator(
        repository,
        checkpoint_manager=GlobalCheckpointManager(settings.federation_checkpoint_dir),
    ).open_round(round_id)
    return round_response(federation_round, repository.participants_for_round(round_id))


@router.post(
    "/rounds/{round_id}/updates/prepare",
    response_model=UpdateArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
def prepare_model_update(
    round_id: UUID,
    request: UpdatePreparationRequest,
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> UpdateArtifactResponse:
    """Reserve one hospital-scoped private-update slot for an open round."""

    submission = ModelUpdateSubmissionService(
        SqlAlchemyFederationRepository(session),
        storage=ModelUpdateArtifactStorage(settings.federation_update_storage_dir),
        max_bytes=settings.federation_update_max_bytes,
    ).prepare(
        principal=principal,
        round_id=round_id,
        model_version_id=request.model_version_id,
    )
    return update_artifact_response(submission)


@router.post("/updates/{submission_id}/artifact", response_model=UpdateArtifactResponse)
async def submit_model_update_artifact(
    submission_id: UUID,
    artifact: UploadFile = File(..., description="Bounded safe model-update ZIP archive."),
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> UpdateArtifactResponse:
    """Accept one bounded archive for the authenticated hospital only."""

    if artifact.filename is None or not artifact.filename.lower().endswith(".zip"):
        from app.core.errors import FederationUpdateRejectedError

        raise FederationUpdateRejectedError("Model update artifact must use the .zip format.")
    try:
        content = await artifact.read(settings.federation_update_max_bytes + 1)
    finally:
        await artifact.close()
    submission = ModelUpdateSubmissionService(
        SqlAlchemyFederationRepository(session),
        storage=ModelUpdateArtifactStorage(settings.federation_update_storage_dir),
        max_bytes=settings.federation_update_max_bytes,
    ).submit_artifact(
        principal=principal,
        submission_id=submission_id,
        content=content,
    )
    return update_artifact_response(submission)


@router.post("/updates/{submission_id}/proof", response_model=UpdateArtifactResponse)
def submit_groth16_proof(
    submission_id: UUID,
    request: Groth16ProofSubmissionRequest,
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> UpdateArtifactResponse:
    """Verify one bounded, server-pinned Groth16 envelope for the caller's update."""

    envelope = Groth16ProofEnvelope(
        circuit_version=request.circuit_version,
        verification_key_id=request.verification_key_id.lower(),
        proofs=tuple(
            Groth16ChunkProof(
                proof=item.proof,
                public_signals=tuple(item.public_signals),
            )
            for item in request.proofs
        ),
    )
    submission = ModelUpdateSubmissionService(
        SqlAlchemyFederationRepository(session),
        storage=ModelUpdateArtifactStorage(settings.federation_update_storage_dir),
        max_bytes=settings.federation_update_max_bytes,
        proof_max_bytes=settings.groth16_proof_max_bytes,
        validator=ModelUpdateValidator(verifier_from_settings(settings)),
    ).submit_proof(
        principal=principal,
        submission_id=submission_id,
        proof_envelope=envelope,
    )
    return update_artifact_response(submission)


@router.get("/updates", response_model=list[UpdateArtifactResponse])
def list_model_update_artifacts(
    principal: Principal = Depends(require_hospital_admin),
    session: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> list[UpdateArtifactResponse]:
    """Return global updates only to operators; scope other admins to their hospital."""

    if principal.hospital_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital identity is required.",
        )

    is_operator = principal.email.lower() in settings.federation_operator_emails

    hospital_scope = None if is_operator else principal.hospital_id

    return [
        update_artifact_response(item)
        for item in SqlAlchemyFederationRepository(session).list_update_artifacts(
            hospital_id=hospital_scope,
        )
    ]

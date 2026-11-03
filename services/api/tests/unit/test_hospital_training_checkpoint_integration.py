"""Synthetic checkpoint-to-training integration tests.

Uses temporary synthetic MRI volumes and a newly initialized
MONAI checkpoint. Never accesses real hospital MRI or production
checkpoint files.
"""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import nibabel as nib
import numpy as np
import pytest
import torch

from app.modules.federation.fedavg import state_dict_sha256
from app.modules.federation.local_training_service import (
    run_hospital_local_training_once,
)
from app.modules.federation.training_agent import (
    LocalTrainingConfiguration,
    TrainingAgentError,
)
from cerebrachain_ml.architecture import build_model


CASE_ID = "BraTS2021_00495"


@pytest.fixture
def training_context(tmp_path):
    torch.manual_seed(42)

    root = tmp_path / "hospital-a"
    directory = root / CASE_ID
    directory.mkdir(parents=True)

    shape = (32, 32, 32)
    affine = np.eye(4)

    rng = np.random.default_rng(42)

    for modality in ("flair", "t1", "t1ce", "t2"):
        data = rng.normal(
            loc=100.0,
            scale=20.0,
            size=shape,
        ).astype(np.float32)

        nib.save(
            nib.Nifti1Image(data, affine),
            directory / f"{CASE_ID}_{modality}.nii.gz",
        )

    labels = np.zeros(shape, dtype=np.uint8)
    labels[8:20, 8:20, 8:20] = 4

    nib.save(
        nib.Nifti1Image(labels, affine),
        directory / f"{CASE_ID}_seg.nii.gz",
    )

    model = build_model()

    checkpoint = tmp_path / "synthetic_model.pth"

    torch.save(
        model.state_dict(),
        checkpoint,
    )

    checkpoint_sha = sha256(
        checkpoint.read_bytes()
    ).hexdigest()

    model_commitment = state_dict_sha256(
        model.state_dict()
    )

    hospital_id = uuid4()

    settings = SimpleNamespace(
        training_execution_enabled=True,
        training_dataset_root=root,
        model_checkpoint_path=checkpoint,
        model_sha256=checkpoint_sha,
        inference_device="cpu",
    )

    principal = SimpleNamespace(
        hospital_id=hospital_id,
        hospital_slug="hospital-a",
    )

    agent = SimpleNamespace(
        hospital_id=hospital_id,
        status="enrolled",
        authorized_case_reference=CASE_ID,
    )

    version = SimpleNamespace(
        model_commitment=model_commitment,
    )

    configuration = LocalTrainingConfiguration(
        local_epochs=1,
        batch_size=1,
        learning_rate=0.0001,
    )

    return SimpleNamespace(
        settings=settings,
        principal=principal,
        agent=agent,
        version=version,
        configuration=configuration,
        checkpoint=checkpoint,
        checkpoint_sha=checkpoint_sha,
        base_state={
            name: tensor.detach().clone()
            for name, tensor in model.state_dict().items()
        },
    )


def execute(context):
    return run_hospital_local_training_once(
        settings=context.settings,
        principal=context.principal,
        agent=context.agent,
        model_version=context.version,
        configuration=context.configuration,
        execution_authorized=True,
    )


def test_verified_checkpoint_local_training(training_context):
    context = training_context

    result = execute(context)

    assert result.optimizer_steps == 1
    assert result.sample_count == 1
    assert result.patch_shape == (32, 32, 32)

    assert len(result.loss_history) == 1
    assert np.isfinite(result.loss_history[0])

    changed = [
        name
        for name, original in context.base_state.items()
        if not torch.equal(
            result.trained_state_dict[name],
            original,
        )
    ]

    assert changed, "Training did not update model weights"

    # The verified checkpoint remains byte-for-byte unchanged.
    assert sha256(
        context.checkpoint.read_bytes()
    ).hexdigest() == context.checkpoint_sha

    print("\nCHECKPOINT VERIFICATION: PASS")
    print("MODEL COMMITMENT: PASS")
    print("LOCAL TRAINING: PASS")
    print("UPDATED STATE TENSORS:", len(changed))
    print("TRAINING LOSS:", result.loss_history[0])
    print("ORIGINAL CHECKPOINT: UNCHANGED")


def test_checkpoint_sha_mismatch_rejected(training_context):
    context = training_context

    context.settings.model_sha256 = "0" * 64

    with pytest.raises(TrainingAgentError):
        execute(context)

    print("\nCHECKPOINT SHA MISMATCH: REJECTED")


def test_model_commitment_mismatch_rejected(training_context):
    context = training_context

    context.version.model_commitment = "0" * 64

    with pytest.raises(TrainingAgentError):
        execute(context)

    print("\nMODEL COMMITMENT MISMATCH: REJECTED")


def test_trained_monai_weights_secure_archive_roundtrip(
    training_context,
) -> None:
    """Verify trained MONAI weights survive the existing safe archive format.

    Synthetic hospital only. No actual federation submission or ZK proof.
    """
    from app.modules.federation.training_agent import HospitalTrainingAgent
    from app.modules.federation.update_archive import (
        parameter_schema_commitment,
        parameter_schema_from_state_dict,
        parse_model_update_archive,
    )
    from app.modules.federation.fedavg import state_dict_sha256

    context = training_context

    # Measure the full synthetic hospital-local execution duration.
    from time import perf_counter

    start = perf_counter()
    result = execute(context)
    execution_seconds = perf_counter() - start

    # Revalidate the approved synthetic checkpoint and model commitment.
    hospital_agent = HospitalTrainingAgent(context.settings)

    preparation = hospital_agent.prepare_training(
        principal=context.principal,
        agent=context.agent,
        model_version=context.version,
        configuration=context.configuration,
    )

    training_metadata = {
        "training_executed": True,
        "local_epochs_completed": 1,
        "training_seconds": execution_seconds,
        "final_loss": float(result.loss_history[-1]),
        "base_checkpoint_sha256": context.checkpoint_sha,
    }

    # Use the existing Phase 2 safe archive builder.
    archive_bytes = hospital_agent.build_authorized_update_archive(
        principal=context.principal,
        agent=context.agent,
        preparation=preparation,
        trained_state_dict=result.trained_state_dict,
        sample_count=result.sample_count,
        training_metadata=training_metadata,
        execution_authorized=True,
    )

    assert isinstance(archive_bytes, bytes)
    assert len(archive_bytes) > 0

    # Existing configured default update-size limit: 64 MiB.
    max_bytes = 64 * 1024 * 1024

    assert len(archive_bytes) <= max_bytes

    # Verify the parameter schema against the approved base model.
    expected_schema = parameter_schema_from_state_dict(
        context.base_state
    )

    expected_schema_hash = parameter_schema_commitment(
        expected_schema
    )

    parsed = parse_model_update_archive(
        archive_bytes,
        expected_schema=expected_schema,
        expected_schema_commitment=expected_schema_hash,
        max_bytes=max_bytes,
    )

    base_commitment = state_dict_sha256(
        context.base_state
    )

    updated_commitment = state_dict_sha256(
        result.trained_state_dict
    )

    assert parsed.model_version_commitment == base_commitment
    assert parsed.update_commitment == updated_commitment

    # The optimizer step must have changed the model commitment.
    assert updated_commitment != base_commitment

    assert parsed.sample_count == 1

    # Compare every tensor, including exact dtype and value.
    assert set(parsed.state_dict) == set(result.trained_state_dict)

    for name, updated_tensor in result.trained_state_dict.items():
        restored_tensor = parsed.state_dict[name]

        assert restored_tensor.dtype == updated_tensor.dtype
        assert restored_tensor.shape == updated_tensor.shape
        assert torch.equal(restored_tensor, updated_tensor), name

    assert parsed.training_metadata is not None
    assert parsed.training_metadata["training_executed"] is True

    assert (
        parsed.training_metadata["base_checkpoint_sha256"]
        == context.checkpoint_sha
    )

    # A valid archive must not imply a submitted or verified ZK proof.
    assert parsed.proof_artifact_reference is None

    # Original checkpoint remains unchanged on disk.
    assert sha256(
        context.checkpoint.read_bytes()
    ).hexdigest() == context.checkpoint_sha

    print("\\n===== SECURE TRAINING ARCHIVE RESULT =====")
    print("VERIFIED CHECKPOINT: PASS")
    print("LOCAL TRAINING: PASS")
    print("ARCHIVE ROUNDTRIP: PASS")
    print("MODEL SCHEMA: PASS")
    print("UPDATE COMMITMENT: PASS")
    print("TENSOR INTEGRITY: PASS")
    print("ARCHIVE SIZE BYTES:", len(archive_bytes))
    print("STATE TENSORS:", len(parsed.state_dict))
    print("ORIGINAL CHECKPOINT: UNCHANGED")
    print("GROTH16 PROOF: NOT SUBMITTED")
    print("FEDERATION SUBMISSION: NOT PERFORMED")

"""Full-model integrity tests using synthetic model weights."""

from __future__ import annotations

import hashlib
from collections import OrderedDict

import pytest
import torch

from app.modules.federation.update_archive import (
    UpdateArchiveError,
    build_model_update_archive,
    parameter_schema_from_state_dict,
)
from app.modules.federation.update_integrity import (
    UpdateIntegrityError,
    verify_pinned_model_update,
)
from cerebrachain_ml.architecture import (
    MODEL_PARAMETER_COUNT,
    build_model,
)


BASE_COMMITMENT = "a" * 64
MAX_BYTES = 64 * 1024 * 1024


def _synthetic_training_metadata() -> dict[str, object]:
    """Test-only metadata, not evidence of actual training."""

    return {
        "training_executed": True,
        "local_epochs_completed": 1,
        "training_seconds": 0.0,
    }


def make_fixture():
    state = OrderedDict(
        weight=torch.tensor(
            [0.1, 0.2, 0.3, 0.4],
            dtype=torch.float32,
        )
    )

    archive = build_model_update_archive(
        state_dict=state,
        model_version_commitment=BASE_COMMITMENT,
        sample_count=1,
        training_metadata=_synthetic_training_metadata(),
    )

    return (
        archive,
        hashlib.sha256(archive).hexdigest(),
        parameter_schema_from_state_dict(state),
    )


def verify(archive, digest, schema):
    return verify_pinned_model_update(
        archive,
        trusted_artifact_sha256=digest,
        trusted_base_model_commitment=BASE_COMMITMENT,
        trusted_parameter_schema=schema,
        max_bytes=MAX_BYTES,
    )


def test_valid_full_update_integrity():
    archive, digest, schema = make_fixture()

    receipt = verify(archive, digest, schema)

    assert receipt.artifact_sha256 == digest
    assert receipt.base_model_commitment == BASE_COMMITMENT
    assert receipt.state_tensor_count == 1
    assert receipt.state_value_count == 4

    # Integrity verification never grants ZK verification.
    assert not hasattr(receipt, "zk_coverage_complete")
    assert not hasattr(receipt, "aggregation_eligible")


def test_artifact_hash_mismatch_rejected():
    archive, _, schema = make_fixture()

    with pytest.raises(
        UpdateIntegrityError,
        match="artifact SHA-256 mismatch",
    ):
        verify(archive, "0" * 64, schema)


def test_base_model_mismatch_rejected():
    archive, digest, schema = make_fixture()

    with pytest.raises(
        UpdateIntegrityError,
        match="trusted base version",
    ):
        verify_pinned_model_update(
            archive,
            trusted_artifact_sha256=digest,
            trusted_base_model_commitment="b" * 64,
            trusted_parameter_schema=schema,
            max_bytes=MAX_BYTES,
        )


def test_modified_archive_rejected():
    archive, digest, schema = make_fixture()

    modified = archive + b"modified"

    with pytest.raises(UpdateIntegrityError):
        verify(modified, digest, schema)


def test_wrong_parameter_schema_rejected():
    archive, digest, _ = make_fixture()

    wrong_state = OrderedDict(
        weight=torch.zeros(10)
    )

    wrong_schema = parameter_schema_from_state_dict(
        wrong_state
    )

    with pytest.raises(UpdateArchiveError):
        verify(archive, digest, wrong_schema)


def test_complete_monai_model_integrity():
    """Verify integrity across the actual full MONAI state schema.

    This test does not train a model or generate a Groth16 proof.
    """

    model = build_model()
    state = model.state_dict()

    assert sum(
        tensor.numel()
        for tensor in state.values()
    ) == MODEL_PARAMETER_COUNT

    archive = build_model_update_archive(
        state_dict=state,
        model_version_commitment=BASE_COMMITMENT,
        sample_count=1,
        training_metadata=_synthetic_training_metadata(),
    )

    receipt = verify(
        archive,
        hashlib.sha256(archive).hexdigest(),
        parameter_schema_from_state_dict(state),
    )

    assert receipt.state_tensor_count == 48
    assert receipt.state_value_count == 2_453_636

    print("\nFULL MONAI MODEL INTEGRITY: PASS")
    print("STATE TENSORS:", receipt.state_tensor_count)
    print("STATE VALUES:", receipt.state_value_count)
    print("GROTH16 PROOF: NOT PERFORMED")
    print("AGGREGATION: NOT PERFORMED")

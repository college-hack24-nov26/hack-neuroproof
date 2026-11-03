"""Real MONAI architecture training compatibility test.

Synthetic tensors only. No hospital data, checkpoint loading,
database access, networking, or checkpoint persistence.
"""

from __future__ import annotations

import math

import torch

from cerebrachain_ml.architecture import (
    MODEL_PARAMETER_COUNT,
    build_model,
    parameter_count,
)
from cerebrachain_ml.local_training import (
    train_local_single_step,
)
from cerebrachain_ml.training_data import (
    PreparedTrainingCase,
)


def test_real_monai_unet_single_training_step() -> None:
    # Limit CPU parallelism for this bounded development test.
    torch.set_num_threads(2)
    torch.manual_seed(42)

    model = build_model()

    assert parameter_count(model) == MODEL_PARAMETER_COUNT

    original_state = {
        name: tensor.detach().clone()
        for name, tensor in model.state_dict().items()
    }

    generator = torch.Generator().manual_seed(123)

    image = torch.randn(
        (1, 4, 32, 32, 32),
        generator=generator,
        dtype=torch.float32,
    )

    target = torch.zeros(
        (1, 32, 32, 32),
        dtype=torch.int64,
    )

    # Synthetic enhancing-tumour class (mapped label 4 -> 3).
    target[:, 8:20, 8:20, 8:20] = 3

    case = PreparedTrainingCase(
        case_reference="BraTS2021_00495",
        image=image,
        target=target,
        original_shape=(32, 32, 32),
    )

    result = train_local_single_step(
        model,
        case,
        execution_enabled=True,
        execution_authorized=True,
        learning_rate=0.0001,
        patch_size=(32, 32, 32),
        max_steps=1,
    )

    assert result.optimizer_steps == 1
    assert result.sample_count == 1
    assert result.patch_shape == (32, 32, 32)

    assert len(result.loss_history) == 1
    assert math.isfinite(result.loss_history[0])
    assert result.loss_history[0] > 0

    # The original MONAI model must remain unchanged.
    for name, original in original_state.items():
        assert torch.equal(
            model.state_dict()[name],
            original,
        ), f"Original model changed: {name}"

    # The training step must actually update some weights.
    changed = [
        name
        for name, original in original_state.items()
        if not torch.equal(
            result.trained_state_dict[name],
            original,
        )
    ]

    assert changed, "No model parameters were updated"

    assert all(
        bool(torch.isfinite(tensor).all().item())
        for tensor in result.trained_state_dict.values()
    )

    print(
        "\nMONAI MODEL PARAMETERS:",
        parameter_count(model),
    )
    print(
        "TRAINING LOSS:",
        result.loss_history[0],
    )
    print(
        "UPDATED STATE TENSORS:",
        len(changed),
    )
    print(
        "OPTIMIZER STEPS:",
        result.optimizer_steps,
    )
    print(
        "ORIGINAL MODEL:",
        "UNCHANGED",
    )

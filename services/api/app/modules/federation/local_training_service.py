"""Internal hospital-local training integration.

No public API endpoint, automatic execution, database writes,
checkpoint persistence, or network submission.

Production use requires a trusted per-run authorization mechanism
in addition to the existing configuration guard.
"""

from __future__ import annotations

from app.core.config import Settings
from app.models.federation import (
    FederationModelVersion,
    FederationTrainingAgent,
)
from app.modules.federation.training_agent import (
    HospitalTrainingAgent,
    LocalTrainingConfiguration,
    TrainingAgentError,
)
from app.services.authentication import Principal

from cerebrachain_ml.local_training import (
    LocalTrainingResult,
    train_local_single_step,
)
from cerebrachain_ml.training_data import (
    load_training_case,
)


def run_hospital_local_training_once(
    *,
    settings: Settings,
    principal: Principal,
    agent: FederationTrainingAgent,
    model_version: FederationModelVersion,
    configuration: LocalTrainingConfiguration,
    execution_authorized: bool = False,
) -> LocalTrainingResult:
    """Run one bounded hospital-local training step.

    Must only be called by a trusted, explicitly authorized
    hospital-local execution context.

    Does not save checkpoints or submit federation updates.
    """

    # Fail closed before loading MRI or checkpoint data.
    if (
        settings.training_execution_enabled is not True
        or execution_authorized is not True
    ):
        raise TrainingAgentError(
            "Hospital-local training execution is disabled."
        )

    # Existing training primitive supports only this
    # bounded one-step development configuration.
    if (
        configuration.local_epochs != 1
        or configuration.batch_size != 1
        or not 0 < configuration.learning_rate <= 0.001
    ):
        raise TrainingAgentError(
            "Unsupported bounded training configuration."
        )

    hospital_agent = HospitalTrainingAgent(settings)

    # Reuse existing authentication and authorization.
    # This verifies the hospital dataset assignment,
    # local MRI geometry, checkpoint SHA-256, and
    # selected model-version commitment.
    preparation = hospital_agent.prepare_training(
        principal=principal,
        agent=agent,
        model_version=model_version,
        configuration=configuration,
    )

    root = settings.training_dataset_root

    if root is None:
        raise TrainingAgentError(
            "Hospital training dataset root is unavailable."
        )

    case_reference = (
        preparation.dataset_geometry.case_reference
    )

    case_directory = root / case_reference

    # Load the authorized case, including ground-truth
    # segmentation labels and BraTS class mapping.
    training_case = load_training_case(
        case_directory,
        case_reference,
    )

    if (
        training_case.case_reference != case_reference
        or tuple(training_case.image.shape)
        != preparation.dataset_geometry.input_shape
    ):
        raise TrainingAgentError(
            "Prepared training dataset does not match "
            "the authorized geometry."
        )

    # The training engine independently clones the model.
    # It returns updated CPU state tensors but does not
    # modify the approved checkpoint on disk.
    return train_local_single_step(
        preparation.model,
        training_case,
        execution_enabled=(
            settings.training_execution_enabled
        ),
        execution_authorized=execution_authorized,
        learning_rate=configuration.learning_rate,
        patch_size=(32, 32, 32),
        max_steps=1,
    )

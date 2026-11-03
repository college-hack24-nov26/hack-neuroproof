"""Exception types raised by the ML adapter."""


class MlAdapterError(Exception):
    """Base exception for a known inference-adapter failure."""


class CheckpointIntegrityError(MlAdapterError):
    """The configured model artifact is absent, malformed, or has the wrong hash."""


class ModelLoadError(MlAdapterError):
    """A checkpoint cannot be loaded into the established model architecture."""


class MriValidationError(MlAdapterError):
    """MRI inputs are incomplete, malformed, misaligned, or non-finite."""


class InferenceError(MlAdapterError):
    """The model did not produce a valid segmentation output."""

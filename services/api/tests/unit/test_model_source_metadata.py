"""Model-provenance metadata survives persistence and old records remain readable."""
from app.models.mri import MriJob


def test_model_source_roundtrip():
    job = MriJob.create()
    job.model_source = "global_fedavg_abc"
    restored = MriJob.from_record(job.to_record())
    assert restored.model_source == "global_fedavg_abc"


def test_legacy_job_defaults_to_local():
    original = MriJob.create().to_record()
    original.pop("model_source")
    assert MriJob.from_record(original).model_source == "local"

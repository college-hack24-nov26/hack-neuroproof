import { ArrowRight, UploadCloud } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MriFileField } from "../components/imaging/MriFileField";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useAsyncData } from "../hooks/useAsyncData";
import {
  mriService,
  type MriFileSet,
  type MriModality,
  type ModelSource,
} from "../services/mriService";
import type { MriJob, MriResult } from "../types/api";
import { getErrorMessage } from "../utils/errors";
import { MRI_MODALITIES, validateMriFile } from "../utils/fileValidation";

type FileState = Record<MriModality, File | null>;
type ErrorState = Record<MriModality, string | undefined>;

const emptyFiles: FileState = { flair: null, t1: null, t1ce: null, t2: null };
const emptyErrors: ErrorState = {
  flair: undefined,
  t1: undefined,
  t1ce: undefined,
  t2: undefined,
};

export function MriAnalysisPage() {
  const [files, setFiles] = useState<FileState>(emptyFiles);
  const [modelSource, setModelSource] = useState<ModelSource>("local");
  const [errors, setErrors] = useState<ErrorState>(emptyErrors);
  const [job, setJob] = useState<MriJob | null>(null);
  const [result, setResult] = useState<MriResult | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();
  const modelInfoState = useAsyncData(
    (signal) => mriService.modelInfo(modelSource, signal),
    [modelSource],
  );
  const selectedCheckpoint = modelInfoState.data?.checkpoint;
  const selectedCheckpointSha = selectedCheckpoint?.sha256 ?? null;
  const modelReady =
    modelInfoState.data?.model_source === modelSource &&
    modelInfoState.data.configured &&
    modelInfoState.data.integrity_status === "verified" &&
    selectedCheckpointSha !== null;
  const isReady = useMemo(
    () =>
      Object.values(files).every((file) => file !== null) &&
      Object.values(errors).every((error) => !error) &&
      modelReady,
    [errors, files, modelReady],
  );

  const setFile = (modality: MriModality, file: File | null) => {
    const validationError = file
      ? validateMriFile(file)
      : "This modality is required.";
    setFiles((current) => ({ ...current, [modality]: file }));
    setErrors((current) => ({
      ...current,
      [modality]: validationError ?? undefined,
    }));
  };

  const submit = async () => {
    const nextErrors = MRI_MODALITIES.reduce<ErrorState>(
      (current, { id }) => ({
        ...current,
        [id]: files[id]
          ? (validateMriFile(files[id] as File) ?? undefined)
          : "This modality is required.",
      }),
      emptyErrors,
    );
    setErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) {
      return;
    }
    if (!modelReady) {
      setSubmissionError(
        modelInfoState.error
          ? `Selected checkpoint is unavailable: ${getErrorMessage(modelInfoState.error)}`
          : "Selected checkpoint is still being verified. Please wait.",
      );
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setSubmissionError(null);
    setProgress(0);
    setJob(null);
    setResult(null);
    try {
      const submittedJob = await mriService.submit(
        files as MriFileSet,
        controller.signal,
        setProgress,
        modelSource,
      );
      setJob(submittedJob);
      const resolvedResult = await mriService.result(
        submittedJob.job_id,
        controller.signal,
      );
      setResult(resolvedResult);
    } catch (error) {
      setSubmissionError(getErrorMessage(error));
    } finally {
      controllerRef.current = null;
      setProgress(null);
    }
  };

  const cancel = () => controllerRef.current?.abort();

  return (
    <div className="grid gap-7">
      <PageHeader
        description="Upload all four required NIfTI modalities. The API validates the configured model and produces a research-only segmentation artifact when authorized."
        title="MRI analysis"
      />
      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <h2 className="font-semibold text-ink">Four-modality upload</h2>
          <p className="mt-1 text-sm leading-6 text-muted">
            Files are sent only when all required modalities have passed
            client-side checks. Server validation remains authoritative.
          </p>
          <fieldset className="mt-5 rounded-lg border border-border p-4">
            <legend className="px-1 text-sm font-semibold text-ink">Inference checkpoint</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex cursor-pointer items-start gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="modelSource"
                  value="local"
                  checked={modelSource === "local"}
                  disabled={progress !== null}
                  onChange={() => setModelSource("local")}
                />
                <span>Original 3D U-Net (local baseline)</span>
              </label>
              <label className="flex cursor-pointer items-start gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="modelSource"
                  value="global_fedavg_abc"
                  checked={modelSource === "global_fedavg_abc"}
                  disabled={progress !== null}
                  onChange={() => setModelSource("global_fedavg_abc")}
                />
                <span>Global FedAvg A+B+C (historical Round 1)</span>
              </label>
            </div>
            <p className="mt-2 text-xs text-muted">
              Both modes use real MRI inference; this does not run a new federated training round.
            </p>
            {modelInfoState.isLoading ? (
              <p className="mt-3 text-xs text-muted" role="status">
                Verifying selected checkpoint before upload…
              </p>
            ) : modelInfoState.error ? (
              <p className="mt-3 text-xs text-rose-200" role="alert">
                Selected checkpoint is unavailable: {getErrorMessage(modelInfoState.error)}
              </p>
            ) : modelReady && selectedCheckpointSha ? (
              <p className="mt-3 break-all text-xs text-emerald-200" role="status">
                Verified checkpoint SHA256: {selectedCheckpointSha}
              </p>
            ) : (
              <p className="mt-3 text-xs text-rose-200" role="alert">
                Selected checkpoint is not configured or did not pass integrity verification.
              </p>
            )}
          </fieldset>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {MRI_MODALITIES.map((modality) => (
              <MriFileField
                description={modality.description}
                error={errors[modality.id]}
                file={files[modality.id]}
                key={modality.id}
                label={modality.label}
                modality={modality.id}
                onChange={(file) => setFile(modality.id, file)}
              />
            ))}
          </div>
          {submissionError ? (
            <p
              className="mt-5 rounded-lg border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100"
              role="alert"
            >
              {submissionError}
            </p>
          ) : null}
          <div className="mt-6 flex flex-wrap gap-3">
            <Button
              disabled={!isReady || progress !== null}
              onClick={() => void submit()}
            >
              <UploadCloud aria-hidden className="h-4 w-4" />
              Submit for analysis
            </Button>
            {progress !== null ? (
              <Button onClick={cancel} variant="ghost">
                Cancel upload
              </Button>
            ) : null}
          </div>
          {progress !== null ? (
            <div aria-label={`Upload progress ${progress}%`} className="mt-5">
              <div className="flex justify-between text-sm text-muted">
                <span>Uploading and processing</span>
                <span>{progress}%</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-700">
                <div
                  className="h-full bg-secondary transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          ) : null}
        </Card>
        <Card className="self-start">
          <h2 className="font-semibold text-ink">Analysis status</h2>
          {job ? (
            <div className="mt-5 grid gap-4">
              <StatusBadge status={job.status} />
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Job ID
                </p>
                <p className="mt-1 break-all font-mono text-sm text-ink">
                  {job.job_id}
                </p>
              </div>
              {result ? (
                <>
                  <p className="text-sm text-emerald-200">
                    A real result is available from the API.
                  </p>
                  <Button
                    onClick={() => navigate(`/app/results/${result.job_id}`)}
                    variant="secondary"
                  >
                    Open result workspace
                    <ArrowRight aria-hidden className="h-4 w-4" />
                  </Button>
                </>
              ) : (
                <p className="text-sm text-muted">
                  Result metadata will appear after the API completes the job.
                </p>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm leading-6 text-muted">
              No analysis has been submitted in this browser session.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

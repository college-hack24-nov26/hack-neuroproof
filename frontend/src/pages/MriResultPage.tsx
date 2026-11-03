import { MriSliceViewer } from "../components/imaging/MriSliceViewer";
import { Download, Search } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { AsyncState } from "../components/ui/AsyncState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { FormField } from "../components/ui/FormField";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useAsyncData } from "../hooks/useAsyncData";
import { mriService } from "../services/mriService";
import { getErrorMessage } from "../utils/errors";

export function MriResultPage() {
  const { jobId } = useParams();
  const [requestedJobId, setRequestedJobId] = useState(jobId ?? "");
  const [lookupId, setLookupId] = useState(jobId ?? "");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const resultState = useAsyncData(
    (signal) =>
      lookupId ? mriService.result(lookupId, signal) : Promise.resolve(null),
    [lookupId],
  );
  const download = async () => {
    if (!resultState.data) return;
    setDownloadError(null);
    try {
      const blob = await mriService.download(resultState.data.job_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${resultState.data.job_id}-segmentation.nii.gz`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setDownloadError(getErrorMessage(error));
    }
  };
  return (
    <div className="grid gap-7">
      <PageHeader
        description="Enter an authorized MRI job ID to retrieve only the metadata and segmentation artifact permitted for your active hospital."
        title="MRI result workspace"
      />
      <Card>
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            setLookupId(requestedJobId.trim());
          }}
        >
          <div className="min-w-0 flex-1">
            <FormField
              label="MRI job ID"
              onChange={(event) => setRequestedJobId(event.target.value)}
              placeholder="UUID returned after analysis"
              value={requestedJobId}
            />
          </div>
          <Button type="submit" variant="ghost">
            <Search aria-hidden className="h-4 w-4" />
            Retrieve result
          </Button>
        </form>
      </Card>
      {!lookupId ? (
        <AsyncState
          detail="Submit an MRI analysis or enter an authorized job ID to view real result metadata."
          kind="empty"
          title="No result selected"
        />
      ) : resultState.isLoading ? (
        <AsyncState
          detail="Requesting authorized result metadata from the API."
          kind="loading"
          title="Loading result"
        />
      ) : resultState.error || !resultState.data ? (
        <AsyncState
          detail="The result is unavailable, incomplete, or outside your hospital scope."
          kind="error"
          title="Result unavailable"
        />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="xl:col-span-2">
            <MriSliceViewer jobId={resultState.data.job_id} />
          </div>
          <Card>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold text-ink">
                  Verified result metadata
                </h2>
                <p className="mt-1 text-sm text-muted">
                  Explore authorized MRI images and real segmentation results above.
                </p>
              </div>
              <StatusBadge status={resultState.data.status} />
            </div>
            <dl className="mt-6 grid gap-5 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Case ID
                </dt>
                <dd className="mt-1 text-sm text-muted">
                  Unavailable: this API result is scoped by job ID.
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Job ID
                </dt>
                <dd className="mt-1 break-all font-mono text-sm text-ink">
                  {resultState.data.job_id}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Inference model
                </dt>
                <dd className="mt-1 text-sm font-semibold text-cyan-200">
                  {resultState.data.model_source === "global_fedavg_abc"
                    ? "Global FedAvg A+B+C — Round 1"
                    : "Original 3D U-Net — local baseline"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Model hash
                </dt>
                <dd className="mt-1 break-all font-mono text-sm text-ink">
                  {resultState.data.model_sha256}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Segmentation shape
                </dt>
                <dd className="mt-1 text-sm text-ink">
                  {resultState.data.segmentation_shape.join(" × ")}
                </dd>
              </div>
            </dl>
          </Card>
          <Card>
            <h2 className="font-semibold text-ink">Tumor statistics</h2>
            <dl className="mt-5 grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-sm text-muted">Tumor voxels</dt>
                <dd className="mt-1 text-2xl font-semibold text-ink">
                  {resultState.data.statistics.tumor_voxels.toLocaleString()}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted">Tumor volume</dt>
                <dd className="mt-1 text-2xl font-semibold text-ink">
                  {resultState.data.statistics.tumor_volume_ml.toFixed(2)} mL
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted">Inference duration</dt>
                <dd className="mt-1 text-lg font-semibold text-ink">
                  {resultState.data.inference_seconds.toFixed(2)} s
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted">Labels</dt>
                <dd className="mt-1 text-lg font-semibold text-ink">
                  {resultState.data.labels.join(", ")}
                </dd>
              </div>
            </dl>
            <Button
              className="mt-7 w-full"
              onClick={() => void download()}
              variant="secondary"
            >
              <Download aria-hidden className="h-4 w-4" />
              Download segmentation
            </Button>
            {downloadError ? (
              <p className="mt-3 text-sm text-rose-200" role="alert">
                {downloadError}
              </p>
            ) : null}
          </Card>
        </div>
      )}
    </div>
  );
}

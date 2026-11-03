import { useEffect, useState } from "react";
import { Card } from "../ui/Card";
import { mriService, type MriModality } from "../../services/mriService";
import { getErrorMessage } from "../../utils/errors";

type Plane = "axial" | "sagittal" | "coronal";

const PLANES: Plane[] = ["axial", "sagittal", "coronal"];

const MODALITIES: { value: MriModality; label: string }[] = [
  { value: "flair", label: "FLAIR" },
  { value: "t1", label: "T1" },
  { value: "t1ce", label: "T1CE" },
  { value: "t2", label: "T2" },
];

function SlicePanel({
  jobId,
  plane,
  modality,
  overlay,
}: {
  jobId: string;
  plane: Plane;
  modality: MriModality;
  overlay: boolean;
}) {
  const [position, setPosition] = useState(50);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let createdUrl: string | null = null;

    setLoading(true);
    setError(null);
    setImageUrl(null);

    const timer = window.setTimeout(async () => {
      try {
        const image = await mriService.slice(
          jobId,
          {
            modality,
            plane,
            position: position / 100,
            overlay,
          },
          controller.signal,
        );

        if (!active) return;

        createdUrl = URL.createObjectURL(image);
        setImageUrl(createdUrl);
      } catch (cause) {
        if (active && !controller.signal.aborted) {
          setError(getErrorMessage(cause));
        }
      } finally {
        if (active) setLoading(false);
      }
    }, 200);

    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();

      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [jobId, plane, modality, position, overlay]);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold capitalize text-slate-100">
          {plane} view
        </h3>
        <span className="text-xs text-slate-400">
          {position}% depth
        </span>
      </div>

      <div className="flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-black">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={`${modality.toUpperCase()} ${plane} MRI slice${overlay ? " with segmentation overlay" : ""}`}
            className="h-full w-full object-contain"
          />
        ) : (
          <p
            className="px-4 text-center text-sm text-slate-400"
            role={error ? "alert" : "status"}
          >
            {error || (loading ? "Loading real MRI slice…" : "No preview")}
          </p>
        )}
      </div>

      <label
        htmlFor={`slice-${plane}`}
        className="mt-4 block text-xs font-medium text-slate-300"
      >
        Slice position
      </label>

      <input
        id={`slice-${plane}`}
        type="range"
        min={0}
        max={100}
        step={1}
        value={position}
        onChange={(event) => setPosition(Number(event.target.value))}
        className="mt-2 w-full accent-violet-500"
        aria-label={`${plane} slice position`}
      />
    </div>
  );
}

export function MriSliceViewer({ jobId }: { jobId: string }) {
  const [modality, setModality] = useState<MriModality>("flair");
  const [overlay, setOverlay] = useState(true);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">
            Interactive MRI Viewer
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Real NIfTI images and model-generated segmentation.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-200">
            Modality
            <select
              value={modality}
              onChange={(event) =>
                setModality(event.target.value as MriModality)
              }
              className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100"
            >
              {MODALITIES.map((item) => (
                <option value={item.value} key={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={overlay}
              onChange={(event) => setOverlay(event.target.checked)}
              className="accent-violet-500"
            />
            Tumour overlay
          </label>
        </div>
      </div>

      <div className="mt-6 grid gap-5 md:grid-cols-3">
        {PLANES.map((plane) => (
          <SlicePanel
            key={`${jobId}-${plane}`}
            jobId={jobId}
            plane={plane}
            modality={modality}
            overlay={overlay}
          />
        ))}
      </div>

      <div className="mt-5 flex flex-wrap gap-4 text-xs text-slate-300">
        <span>🔴 Label 1 — Tumour core</span>
        <span>🔵 Label 2 — Edema</span>
        <span>🟣 Label 4 — Enhancing tumour</span>
      </div>

      <p className="mt-3 text-xs text-slate-400">
        Research visualization only. Slice percentage is a relative
        position, not a physical anatomical coordinate. Not for
        clinical diagnosis.
      </p>
    </Card>
  );
}

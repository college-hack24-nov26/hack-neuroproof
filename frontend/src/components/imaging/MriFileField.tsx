import { CheckCircle2, FileUp } from "lucide-react";
import type { MriModality } from "../../services/mriService";

interface MriFileFieldProps {
  modality: MriModality;
  label: string;
  description: string;
  file: File | null;
  error?: string;
  onChange: (file: File | null) => void;
}

export function MriFileField({
  description,
  error,
  file,
  label,
  modality,
  onChange,
}: MriFileFieldProps) {
  const inputId = `mri-${modality}`;
  return (
    <div className="rounded-xl border border-border bg-slate-900/20 p-4">
      <div className="flex items-start gap-3">
        <FileUp aria-hidden className="mt-0.5 h-5 w-5 text-secondary" />
        <div className="min-w-0 flex-1">
          <label className="font-semibold text-ink" htmlFor={inputId}>
            {label}
          </label>
          <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
          <input
            accept=".nii,.nii.gz,application/octet-stream,application/gzip"
            aria-describedby={`${inputId}-description`}
            className="mt-4 block w-full text-sm text-muted file:mr-4 file:rounded-md file:border-0 file:bg-primary/20 file:px-3 file:py-2 file:text-sm file:font-semibold file:text-violet-100 hover:file:bg-primary/30"
            id={inputId}
            onChange={(event) => onChange(event.target.files?.[0] ?? null)}
            type="file"
          />
          <div className="mt-3 min-h-5 text-xs" id={`${inputId}-description`}>
            {error ? (
              <span className="text-rose-200">{error}</span>
            ) : file ? (
              <span className="inline-flex items-center gap-1 text-emerald-200">
                <CheckCircle2 aria-hidden className="h-3.5 w-3.5" />
                {file.name}
              </span>
            ) : (
              <span className="text-muted">
                Required · .nii or .nii.gz · max 64 MB
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

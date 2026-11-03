import type { MriJob, MriModelInfo, MriResult } from "../types/api";
import { apiClient } from "./apiClient";

export type MriModality = "flair" | "t1" | "t1ce" | "t2";
export type ModelSource = "local" | "global_fedavg_abc";
export type MriFileSet = Record<MriModality, File>;

export const mriService = {
  modelInfo: (modelSource: ModelSource, signal?: AbortSignal) =>
    apiClient.request<MriModelInfo>(
      `/model/info?model_source=${encodeURIComponent(modelSource)}`,
      { signal },
    ),
  submit: (
    files: MriFileSet,
    signal?: AbortSignal,
    onProgress?: (percent: number) => void,
    modelSource: ModelSource = "local",
  ) => {
    const data = new FormData();
    data.append("model_source", modelSource);
    (Object.entries(files) as [MriModality, File][]).forEach(
      ([modality, file]) => {
        data.append(modality, file, file.name);
      },
    );
    return apiClient.upload<MriJob>("/mri/segment", {
      data,
      signal,
      onProgress,
    });
  },
  job: (jobId: string, signal?: AbortSignal) =>
    apiClient.request<MriJob>(`/mri/jobs/${jobId}`, { signal }),
  result: (jobId: string, signal?: AbortSignal) =>
    apiClient.request<MriResult>(`/mri/jobs/${jobId}/result`, { signal }),
  slice: (
    jobId: string,
    options: {
      modality: MriModality;
      plane: "axial" | "sagittal" | "coronal";
      position: number;
      overlay: boolean;
    },
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams({
      modality: options.modality,
      plane: options.plane,
      position: String(options.position),
      overlay: String(options.overlay),
    });

    return apiClient.download(
      `/mri/jobs/${encodeURIComponent(jobId)}/slice?${params.toString()}`,
      signal,
    );
  },
  download: (jobId: string, signal?: AbortSignal) =>
    apiClient.download(`/mri/jobs/${jobId}/result?download=true`, signal),
};

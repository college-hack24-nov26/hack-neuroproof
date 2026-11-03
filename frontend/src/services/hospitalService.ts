import type {
  DoctorListResponse,
  Hospital,
  MriCaseListResponse,
} from "../types/api";
import { apiClient } from "./apiClient";

export const hospitalService = {
  current: (signal?: AbortSignal) =>
    apiClient.request<Hospital>("/hospitals/me", { signal }),
  doctors: (signal?: AbortSignal) =>
    apiClient.request<DoctorListResponse>("/hospitals/me/doctors", { signal }),
  cases: (signal?: AbortSignal) =>
    apiClient.request<MriCaseListResponse>("/hospitals/me/mri-cases", {
      signal,
    }),
};

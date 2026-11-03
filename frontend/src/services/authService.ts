import type { AccessTokenResponse, Actor } from "../types/api";
import { apiClient } from "./apiClient";

export interface LoginPayload {
  email: string;
  password: string;
  hospital_slug: string;
}

export interface HospitalRegistrationPayload {
  hospital_name: string;
  administrator_name: string;
  email: string;
  password: string;
}

export interface DoctorCreatePayload {
  full_name: string;
  email: string;
  password: string;
}

export const authService = {
  login: (payload: LoginPayload, signal?: AbortSignal) =>
    apiClient.request<AccessTokenResponse>("/auth/login", {
      method: "POST",
      authenticated: false,
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  registerHospital: (
    payload: HospitalRegistrationPayload,
    signal?: AbortSignal,
  ) =>
    apiClient.request<AccessTokenResponse>("/auth/hospitals/register", {
      method: "POST",
      authenticated: false,
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  me: (signal?: AbortSignal) =>
    apiClient.request<Actor>("/auth/me", { signal }),
  logout: (signal?: AbortSignal) =>
    apiClient.request<void>("/auth/logout", { method: "POST", signal }),
  createDoctor: (payload: DoctorCreatePayload, signal?: AbortSignal) =>
    apiClient.request<Actor>("/hospitals/me/doctors", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};

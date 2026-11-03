import { createContext } from "react";
import type { AccessTokenResponse, Actor, HospitalRole } from "../types/api";
import type {
  HospitalRegistrationPayload,
  LoginPayload,
} from "../services/authService";

export interface AuthContextValue {
  actor: Actor | null;
  isAuthenticated: boolean;
  isInitializing: boolean;
  sessionMessage: string | null;
  login: (
    payload: LoginPayload,
    expectedRole: HospitalRole,
  ) => Promise<AccessTokenResponse>;
  registerHospital: (
    payload: HospitalRegistrationPayload,
  ) => Promise<AccessTokenResponse>;
  logout: () => Promise<void>;
  clearSessionMessage: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

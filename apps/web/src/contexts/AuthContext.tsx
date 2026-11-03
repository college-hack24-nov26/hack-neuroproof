import { useCallback, useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import { AuthContext, type AuthContextValue } from "./authContextValue";
import type { AccessTokenResponse, Actor, HospitalRole } from "../types/api";
import { apiClient } from "../services/apiClient";
import {
  authService,
  type HospitalRegistrationPayload,
  type LoginPayload,
} from "../services/authService";

export function AuthProvider({ children }: PropsWithChildren) {
  const [actor, setActor] = useState<Actor | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [isInitializing] = useState(false);

  const clearSession = useCallback((message?: string) => {
    apiClient.setAccessToken(null);
    setActor(null);
    setExpiresAt(null);
    setSessionMessage(message ?? null);
  }, []);

  useEffect(() => {
    apiClient.setUnauthorizedHandler(() =>
      clearSession("Your session has expired. Please sign in again."),
    );
    return () => apiClient.setUnauthorizedHandler(null);
  }, [clearSession]);

  useEffect(() => {
    if (!expiresAt) {
      return undefined;
    }
    const remaining = new Date(expiresAt).getTime() - Date.now();
    if (remaining <= 0) {
      clearSession("Your session has expired. Please sign in again.");
      return undefined;
    }
    const timeout = window.setTimeout(
      () => clearSession("Your session has expired. Please sign in again."),
      remaining,
    );
    return () => window.clearTimeout(timeout);
  }, [clearSession, expiresAt]);

  const establishSession = useCallback(
    async (response: AccessTokenResponse) => {
      apiClient.setAccessToken(response.access_token);
      try {
        const actor = await authService.me();
        setActor(actor);
        setExpiresAt(response.expires_at);
        setSessionMessage(null);
      } catch (error) {
        clearSession();
        throw error;
      }
    },
    [clearSession],
  );

  const login = useCallback(
    async (payload: LoginPayload, expectedRole: HospitalRole) => {
      const response = await authService.login(payload);
      if (response.actor.role !== expectedRole) {
        apiClient.setAccessToken(response.access_token);
        await authService.logout().catch(() => undefined);
        clearSession();
        throw new Error(
          `This account is not authorized for the ${expectedRole === "doctor" ? "doctor" : "hospital administrator"} portal.`,
        );
      }
      await establishSession(response);
      return response;
    },
    [clearSession, establishSession],
  );

  const registerHospital = useCallback(
    async (payload: HospitalRegistrationPayload) => {
      const response = await authService.registerHospital(payload);
      await establishSession(response);
      return response;
    },
    [establishSession],
  );

  const logout = useCallback(async () => {
    try {
      if (actor) {
        await authService.logout();
      }
    } finally {
      clearSession();
    }
  }, [actor, clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      actor,
      isAuthenticated: actor !== null,
      isInitializing,
      sessionMessage,
      login,
      registerHospital,
      logout,
      clearSessionMessage: () => setSessionMessage(null),
    }),
    [actor, isInitializing, login, logout, registerHospital, sessionMessage],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

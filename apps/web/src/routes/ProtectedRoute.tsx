import { Navigate, Outlet, useLocation } from "react-router-dom";
import { AsyncState } from "../components/ui/AsyncState";
import { useAuth } from "../hooks/useAuth";
import type { HospitalRole } from "../types/api";

interface ProtectedRouteProps {
  allowedRoles?: HospitalRole[];
}

export function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const { actor, isInitializing } = useAuth();
  const location = useLocation();

  if (isInitializing) {
    return (
      <AsyncState
        detail="Restoring the active secure session."
        kind="loading"
        title="Checking access"
      />
    );
  }

  if (!actor) {
    return <Navigate replace state={{ from: location }} to="/hospital-login" />;
  }

  if (allowedRoles && !allowedRoles.includes(actor.role)) {
    return <Navigate replace to="/app" />;
  }

  return <Outlet />;
}

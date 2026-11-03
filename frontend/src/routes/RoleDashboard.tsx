import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { DoctorDashboardPage } from "../pages/DoctorDashboardPage";
import { HospitalDashboardPage } from "../pages/HospitalDashboardPage";

export function RoleDashboard() {
  const { actor } = useAuth();

  if (actor?.role === "hospital_admin") {
    return <HospitalDashboardPage />;
  }

  if (actor?.role === "doctor") {
    return <DoctorDashboardPage />;
  }

  return <Navigate replace to="/hospital-login" />;
}

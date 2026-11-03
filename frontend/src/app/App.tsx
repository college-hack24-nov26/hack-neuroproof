import { BlockchainTrustPage } from "../pages/BlockchainTrustPage";
import { FederationDashboardPage } from "../pages/FederationDashboardPage";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "../layouts/AppShell";
import { DoctorDashboardPage } from "../pages/DoctorDashboardPage";
import { HospitalDashboardPage } from "../pages/HospitalDashboardPage";
import { LandingPage } from "../pages/LandingPage";
import { MriAnalysisPage } from "../pages/MriAnalysisPage";
import { MriResultPage } from "../pages/MriResultPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { HospitalRegistrationPage } from "../pages/auth/HospitalRegistrationPage";
import { LoginPage } from "../pages/auth/LoginPage";
import { ProtectedRoute } from "../routes/ProtectedRoute";
import { RoleDashboard } from "../routes/RoleDashboard";

export function App() {
  return (
    <Routes>
      <Route element={<LandingPage />} path="/" />
      <Route
        element={<LoginPage role="hospital_admin" />}
        path="/hospital-login"
      />
      <Route element={<LoginPage role="doctor" />} path="/doctor-login" />
      <Route element={<HospitalRegistrationPage />} path="/register" />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />} path="/app">
          <Route element={<RoleDashboard />} index />
          <Route element={<MriAnalysisPage />} path="mri-analysis" />
          <Route element={<MriResultPage />} path="results" />
          <Route element={<MriResultPage />} path="results/:jobId" />
          <Route element={<ProtectedRoute allowedRoles={["hospital_admin"]} />}>
            <Route element={<HospitalDashboardPage />} path="hospital" />
            <Route element={<FederationDashboardPage />} path="federation" />
            <Route element={<BlockchainTrustPage />} path="blockchain" />
            <Route element={<HospitalDashboardPage />} path="doctors" />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={["doctor"]} />}>
            <Route element={<DoctorDashboardPage />} path="doctor" />
          </Route>
        </Route>
      </Route>
      <Route element={<NotFoundPage />} path="*" />
    </Routes>
  );
}

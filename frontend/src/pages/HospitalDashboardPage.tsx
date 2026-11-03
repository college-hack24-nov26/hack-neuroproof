import { ScanLine } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { CaseList } from "../components/dashboard/CaseList";
import { DoctorManager } from "../components/dashboard/DoctorManager";
import { AsyncState } from "../components/ui/AsyncState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { useAsyncData } from "../hooks/useAsyncData";
import { hospitalService } from "../services/hospitalService";
import type { Doctor } from "../types/api";

export function HospitalDashboardPage() {
  const hospital = useAsyncData(
    (signal) => hospitalService.current(signal),
    [],
  );
  const doctorData = useAsyncData(
    (signal) => hospitalService.doctors(signal),
    [],
  );
  const caseData = useAsyncData((signal) => hospitalService.cases(signal), []);
  const [createdDoctors, setCreatedDoctors] = useState<Doctor[]>([]);
  const doctors = [...(doctorData.data?.doctors ?? []), ...createdDoctors];
  const appendDoctor = (doctor: Doctor) => {
    setCreatedDoctors((current) => [...current, doctor]);
  };

  if (hospital.isLoading || doctorData.isLoading || caseData.isLoading)
    return (
      <AsyncState
        detail="Reading the active hospital context and authorized metadata."
        kind="loading"
        title="Loading hospital workspace"
      />
    );
  if (hospital.error || doctorData.error || caseData.error)
    return (
      <AsyncState
        detail="The hospital dashboard could not be loaded from the API. Check your connection or sign in again."
        kind="error"
        title="Hospital data unavailable"
      />
    );
  if (!hospital.data || !doctorData.data || !caseData.data)
    return (
      <AsyncState
        detail="No hospital context is available."
        kind="empty"
        title="No data available"
      />
    );

  return (
    <div className="grid gap-7">
      <PageHeader
        actions={
          <Link to="/app/mri-analysis">
            <Button>
              <ScanLine aria-hidden className="h-4 w-4" />
              New MRI analysis
            </Button>
          </Link>
        }
        description="Manage authorized accounts and review metadata belonging to the active hospital only."
        title={hospital.data.name}
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-sm text-muted">Role</p>
          <p className="mt-2 font-semibold capitalize text-ink">
            {hospital.data.role.replaceAll("_", " ")}
          </p>
        </Card>
        <Card>
          <p className="text-sm text-muted">Doctor accounts</p>
          <p className="mt-2 text-2xl font-semibold text-ink">
            {doctors.length}
          </p>
        </Card>
        <Card>
          <p className="text-sm text-muted">MRI cases</p>
          <p className="mt-2 text-2xl font-semibold text-ink">
            {caseData.data.cases.length}
          </p>
        </Card>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <DoctorManager doctors={doctors} onDoctorCreated={appendDoctor} />
        <CaseList cases={caseData.data.cases} />
      </div>
    </div>
  );
}

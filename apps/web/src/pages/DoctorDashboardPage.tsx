import { ArrowRight, ScanLine } from "lucide-react";
import { Link } from "react-router-dom";
import { CaseList } from "../components/dashboard/CaseList";
import { AsyncState } from "../components/ui/AsyncState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { useAuth } from "../hooks/useAuth";
import { useAsyncData } from "../hooks/useAsyncData";
import { hospitalService } from "../services/hospitalService";

export function DoctorDashboardPage() {
  const { actor } = useAuth();
  const caseData = useAsyncData((signal) => hospitalService.cases(signal), []);
  if (caseData.isLoading)
    return (
      <AsyncState
        detail="Reading the MRI cases you are authorized to access."
        kind="loading"
        title="Loading doctor workspace"
      />
    );
  if (caseData.error || !caseData.data)
    return (
      <AsyncState
        detail="The authorized case list could not be loaded."
        kind="error"
        title="Doctor workspace unavailable"
      />
    );
  return (
    <div className="grid gap-7">
      <PageHeader
        actions={
          <Link to="/app/mri-analysis">
            <Button>
              <ScanLine aria-hidden className="h-4 w-4" />
              Start MRI analysis
            </Button>
          </Link>
        }
        description="Review only the MRI cases made available through your active hospital membership."
        title={`Welcome, ${actor?.full_name ?? "Doctor"}`}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <p className="text-sm text-muted">Active hospital</p>
          <p className="mt-2 font-semibold text-ink">{actor?.hospital_name}</p>
          <p className="mt-1 text-sm text-muted">{actor?.hospital_slug}</p>
        </Card>
        <Card>
          <p className="text-sm text-muted">Recent analysis jobs</p>
          <p className="mt-2 text-sm leading-6 text-muted">
            A hospital-scoped job list endpoint is not available yet. Use a
            known authorized job ID in the result workspace.
          </p>
          <Link
            className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-secondary hover:underline"
            to="/app/results"
          >
            <ArrowRight aria-hidden className="h-4 w-4" />
            Open result workspace
          </Link>
        </Card>
      </div>
      <CaseList cases={caseData.data.cases} />
    </div>
  );
}

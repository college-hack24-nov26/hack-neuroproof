import { ArrowRight, Building2, LockKeyhole, ScanLine } from "lucide-react";
import { Link } from "react-router-dom";
import { Brand } from "../components/Brand";
import { Card } from "../components/ui/Card";

const principles = [
  {
    icon: Building2,
    title: "Hospital-scoped",
    copy: "Access and MRI ownership are isolated by verified hospital membership.",
  },
  {
    icon: ScanLine,
    title: "Multi-modal workflow",
    copy: "The analysis pathway requires FLAIR, T1, T1CE, and T2 NIfTI inputs.",
  },
  {
    icon: LockKeyhole,
    title: "Evidence-aware",
    copy: "Model outputs, federation, and trust states are shown only when backend evidence exists.",
  },
];

export function LandingPage() {
  return (
    <main className="min-h-screen bg-canvas text-ink">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
        <Brand />
        <div className="flex items-center gap-3">
          <Link
            className="text-sm font-medium text-muted hover:text-ink"
            to="/register"
          >
            Register hospital
          </Link>
          <Link
            className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-500"
            to="/hospital-login"
          >
            Sign in
          </Link>
        </div>
      </header>
      <section className="mx-auto grid max-w-7xl gap-12 px-5 py-16 sm:px-8 lg:grid-cols-[1.15fr_0.85fr] lg:py-24">
        <div className="self-center">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-secondary">
            Research-only neuroimaging platform
          </p>
          <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
            A hospital-aware foundation for collaborative MRI analysis.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-muted">
            ZKP-CerebraChain V2 connects authorized hospital teams to a verified
            MRI segmentation workflow while keeping identity, tenancy, and
            protected artifacts on the server side.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-3 font-semibold text-white hover:bg-violet-500"
              to="/hospital-login"
            >
              Hospital administrator{" "}
              <ArrowRight aria-hidden className="h-4 w-4" />
            </Link>
            <Link
              className="inline-flex items-center gap-2 rounded-lg border border-border px-5 py-3 font-semibold text-ink hover:bg-slate-800"
              to="/doctor-login"
            >
              Doctor sign in
            </Link>
          </div>
        </div>
        <Card className="relative overflow-hidden bg-sidebar p-7">
          <div className="absolute inset-x-0 top-0 h-1 bg-secondary" />
          <p className="text-sm font-semibold text-secondary">
            Workflow boundary
          </p>
          <ol className="mt-7 grid gap-5">
            <li className="flex gap-4">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/20 text-sm font-bold text-violet-200">
                1
              </span>
              <div>
                <h2 className="font-semibold">Authenticate</h2>
                <p className="mt-1 text-sm leading-6 text-muted">
                  Resolve a hospital administrator or doctor membership from the
                  signed token.
                </p>
              </div>
            </li>
            <li className="flex gap-4">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/20 text-sm font-bold text-violet-200">
                2
              </span>
              <div>
                <h2 className="font-semibold">Submit four modalities</h2>
                <p className="mt-1 text-sm leading-6 text-muted">
                  Upload authorized FLAIR, T1, T1CE, and T2 NIfTI files for
                  model processing.
                </p>
              </div>
            </li>
            <li className="flex gap-4">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/20 text-sm font-bold text-violet-200">
                3
              </span>
              <div>
                <h2 className="font-semibold">Review recorded output</h2>
                <p className="mt-1 text-sm leading-6 text-muted">
                  Inspect server-provided segmentation metadata and download
                  only authorized artifacts.
                </p>
              </div>
            </li>
          </ol>
        </Card>
      </section>
      <section className="mx-auto grid max-w-7xl gap-4 px-5 pb-16 sm:grid-cols-3 sm:px-8 lg:pb-24">
        {principles.map(({ copy, icon: Icon, title }) => (
          <Card key={title}>
            <Icon aria-hidden className="h-6 w-6 text-secondary" />
            <h2 className="mt-5 font-semibold">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted">{copy}</p>
          </Card>
        ))}
      </section>
    </main>
  );
}

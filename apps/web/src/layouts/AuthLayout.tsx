import type { PropsWithChildren } from "react";
import { Brand } from "../components/Brand";

export function AuthLayout({ children }: PropsWithChildren) {
  return (
    <main className="min-h-screen bg-canvas px-4 py-8 sm:px-8 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(25rem,34rem)] lg:gap-12 lg:px-16">
      <section className="hidden max-w-2xl self-center lg:block">
        <Brand />
        <p className="mt-16 text-sm font-semibold uppercase tracking-[0.18em] text-secondary">
          Hospital-scoped research workflow
        </p>
        <h1 className="mt-4 text-5xl font-semibold leading-tight tracking-tight text-ink">
          Collaborative MRI analysis with clear ownership boundaries.
        </h1>
        <p className="mt-6 max-w-xl text-lg leading-8 text-muted">
          Access is issued for one verified hospital membership at a time. The
          platform presents research workflow information, not clinical advice.
        </p>
        <div className="mt-12 grid grid-cols-3 gap-4 text-sm text-muted">
          <div className="border-l-2 border-secondary pl-3">
            Hospital-scoped cases
          </div>
          <div className="border-l-2 border-primary pl-3">
            Verified model provenance
          </div>
          <div className="border-l-2 border-success pl-3">
            Real result artifacts
          </div>
        </div>
      </section>
      <section className="mx-auto flex w-full max-w-xl flex-col lg:justify-center">
        {children}
      </section>
    </main>
  );
}

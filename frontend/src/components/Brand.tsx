import { BrainCircuit } from "lucide-react";
import { Link } from "react-router-dom";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      aria-label="ZKP-CerebraChain home"
      className="inline-flex items-center gap-3"
      to="/"
    >
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/15 text-secondary ring-1 ring-secondary/30">
        <BrainCircuit aria-hidden className="h-6 w-6" />
      </span>
      {!compact ? (
        <span>
          <span className="block text-base font-bold tracking-tight text-ink">
            ZKP-CerebraChain
          </span>
          <span className="block text-xs text-muted">
            Research neuroimaging network
          </span>
        </span>
      ) : null}
    </Link>
  );
}

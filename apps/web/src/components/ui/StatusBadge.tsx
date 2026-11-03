interface StatusBadgeProps {
  status: string;
}

const styles: Record<string, string> = {
  completed: "border-success/40 bg-success/10 text-emerald-200",
  running: "border-secondary/40 bg-secondary/10 text-cyan-100",
  queued: "border-primary/40 bg-primary/10 text-violet-100",
  failed: "border-rose-400/40 bg-rose-400/10 text-rose-100",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${styles[status] ?? "border-border text-muted"}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

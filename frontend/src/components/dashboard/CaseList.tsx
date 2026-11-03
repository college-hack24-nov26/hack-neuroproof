import type { MriCase } from "../../types/api";
import { Card } from "../ui/Card";

export function CaseList({ cases }: { cases: MriCase[] }) {
  return (
    <Card>
      <h2 className="font-semibold text-ink">Authorized MRI cases</h2>
      <p className="mt-1 text-sm text-muted">
        The server returns de-identified case references only.
      </p>
      {cases.length === 0 ? (
        <p className="mt-5 rounded-lg border border-dashed border-border p-4 text-sm text-muted">
          No MRI cases are currently available for this hospital.
        </p>
      ) : (
        <ul className="mt-5 divide-y divide-border">
          {cases.map((item) => (
            <li
              className="flex items-center justify-between gap-4 py-3"
              key={item.id}
            >
              <span className="font-medium text-ink">
                {item.case_reference}
              </span>
              <time className="text-xs text-muted" dateTime={item.created_at}>
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: "medium",
                }).format(new Date(item.created_at))}
              </time>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

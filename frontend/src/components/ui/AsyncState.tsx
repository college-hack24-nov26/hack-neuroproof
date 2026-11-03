import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import { Card } from "./Card";

interface AsyncStateProps {
  title: string;
  detail: string;
  kind: "loading" | "error" | "empty";
}

export function AsyncState({ detail, kind, title }: AsyncStateProps) {
  const Icon =
    kind === "loading" ? LoaderCircle : kind === "error" ? AlertCircle : Inbox;
  return (
    <Card className="flex min-h-36 flex-col items-center justify-center gap-3 text-center">
      <Icon
        aria-hidden
        className={`h-6 w-6 ${kind === "error" ? "text-rose-300" : "text-secondary"} ${kind === "loading" ? "animate-spin" : ""}`}
      />
      <div>
        <h2 className="font-semibold text-ink">{title}</h2>
        <p className="mt-1 max-w-md text-sm text-muted">{detail}</p>
      </div>
    </Card>
  );
}

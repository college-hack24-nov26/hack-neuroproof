import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-6 text-center text-ink">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-secondary">
          404
        </p>
        <h1 className="mt-3 text-3xl font-semibold">Page not found</h1>
        <p className="mt-3 text-muted">
          The requested workspace does not exist.
        </p>
        <Link className="mt-7 inline-block" to="/">
          <Button>Return home</Button>
        </Link>
      </div>
    </main>
  );
}

import { UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { authService } from "../../services/authService";
import type { Doctor } from "../../types/api";
import { getErrorMessage } from "../../utils/errors";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { FormField } from "../ui/FormField";

interface DoctorManagerProps {
  doctors: Doctor[];
  onDoctorCreated: (doctor: Doctor) => void;
}

export function DoctorManager({
  doctors,
  onDoctorCreated,
}: DoctorManagerProps) {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const update = (field: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [field]: value }));
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const actor = await authService.createDoctor(form);
      onDoctorCreated({
        user_id: actor.user_id,
        full_name: actor.full_name,
        email: actor.email,
        created_at: new Date().toISOString(),
      });
      setForm({ full_name: "", email: "", password: "" });
      setIsFormOpen(false);
    } catch (submissionError) {
      setError(getErrorMessage(submissionError));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-ink">Doctor accounts</h2>
          <p className="mt-1 text-sm text-muted">
            Only this hospital&apos;s administrator can create or view these
            accounts.
          </p>
        </div>
        <Button
          onClick={() => setIsFormOpen((current) => !current)}
          variant="ghost"
        >
          <UserPlus aria-hidden className="h-4 w-4" />
          {isFormOpen ? "Close form" : "Add doctor"}
        </Button>
      </div>
      {isFormOpen ? (
        <form
          className="mt-5 grid gap-4 border-t border-border pt-5 sm:grid-cols-2"
          onSubmit={(event) => void submit(event)}
        >
          <FormField
            label="Full name"
            onChange={(event) => update("full_name", event.target.value)}
            required
            value={form.full_name}
          />
          <FormField
            label="Email"
            onChange={(event) => update("email", event.target.value)}
            required
            type="email"
            value={form.email}
          />
          <FormField
            hint="At least 12 characters."
            label="Temporary password"
            onChange={(event) => update("password", event.target.value)}
            required
            type="password"
            value={form.password}
          />
          {error ? (
            <p
              className="self-center text-sm text-rose-200 sm:col-span-2"
              role="alert"
            >
              {error}
            </p>
          ) : null}
          <div className="sm:col-span-2">
            <Button isLoading={isSubmitting} type="submit">
              Create doctor account
            </Button>
          </div>
        </form>
      ) : null}
      {doctors.length === 0 ? (
        <p className="mt-6 rounded-lg border border-dashed border-border p-4 text-sm text-muted">
          No doctor accounts are available for this hospital yet.
        </p>
      ) : (
        <ul className="mt-5 divide-y divide-border">
          {doctors.map((doctor) => (
            <li
              className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between"
              key={doctor.user_id}
            >
              <span className="font-medium text-ink">{doctor.full_name}</span>
              <span className="text-sm text-muted">{doctor.email}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

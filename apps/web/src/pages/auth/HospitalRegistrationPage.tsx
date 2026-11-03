import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FormField } from "../../components/ui/FormField";
import { useAuth } from "../../hooks/useAuth";
import { AuthLayout } from "../../layouts/AuthLayout";
import { getErrorMessage } from "../../utils/errors";

export function HospitalRegistrationPage() {
  const [form, setForm] = useState({
    hospital_name: "",
    administrator_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { registerHospital } = useAuth();
  const navigate = useNavigate();

  const update = (field: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [field]: value }));
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (form.password.length < 12) {
      setError("Use a password with at least 12 characters.");
      return;
    }
    setIsSubmitting(true);
    try {
      await registerHospital(form);
      navigate("/app", { replace: true });
    } catch (submissionError) {
      setError(getErrorMessage(submissionError));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <Card className="w-full p-6 sm:p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-secondary">
          Hospital onboarding
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-ink">
          Register a hospital
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Create the first hospital administrator account. Use synthetic or
          approved de-identified information only.
        </p>
        {error ? (
          <p
            className="mt-5 rounded-lg border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        <form
          className="mt-6 grid gap-5"
          onSubmit={(event) => void submit(event)}
        >
          <FormField
            label="Hospital name"
            onChange={(event) => update("hospital_name", event.target.value)}
            required
            value={form.hospital_name}
          />
          <FormField
            autoComplete="name"
            label="Administrator name"
            onChange={(event) =>
              update("administrator_name", event.target.value)
            }
            required
            value={form.administrator_name}
          />
          <FormField
            autoComplete="email"
            label="Administrator email"
            onChange={(event) => update("email", event.target.value)}
            required
            type="email"
            value={form.email}
          />
          <FormField
            autoComplete="new-password"
            hint="At least 12 characters."
            label="Password"
            onChange={(event) => update("password", event.target.value)}
            required
            type="password"
            value={form.password}
          />
          <Button className="w-full" isLoading={isSubmitting} type="submit">
            Create hospital account
          </Button>
        </form>
        <p className="mt-6 text-sm text-muted">
          Already registered?{" "}
          <Link className="text-secondary hover:underline" to="/hospital-login">
            Sign in as hospital administrator
          </Link>
        </p>
      </Card>
    </AuthLayout>
  );
}

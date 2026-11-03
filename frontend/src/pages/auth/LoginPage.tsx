import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FormField } from "../../components/ui/FormField";
import { useAuth } from "../../hooks/useAuth";
import { AuthLayout } from "../../layouts/AuthLayout";
import type { HospitalRole } from "../../types/api";
import { getErrorMessage } from "../../utils/errors";

interface LoginPageProps {
  role: HospitalRole;
}

export function LoginPage({ role }: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [hospitalSlug, setHospitalSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { clearSessionMessage, login, sessionMessage } = useAuth();
  const navigate = useNavigate();
  const roleLabel = role === "doctor" ? "Doctor" : "Hospital administrator";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login({ email, password, hospital_slug: hospitalSlug }, role);
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
          Secure sign in
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-ink">
          {roleLabel} login
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Enter the hospital slug that your administrator provided. Your role is
          verified by the API after authentication.
        </p>
        {sessionMessage ? (
          <div className="mt-5 rounded-lg border border-amber-300/30 bg-amber-200/10 p-3 text-sm text-amber-100">
            <span>{sessionMessage}</span>
            <button
              className="ml-3 underline"
              onClick={clearSessionMessage}
              type="button"
            >
              Dismiss
            </button>
          </div>
        ) : null}
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
            autoComplete="organization"
            label="Hospital slug"
            onChange={(event) => setHospitalSlug(event.target.value)}
            placeholder="example-research-hospital"
            required
            value={hospitalSlug}
          />
          <FormField
            autoComplete="email"
            label="Email address"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <FormField
            autoComplete="current-password"
            label="Password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          <Button className="w-full" isLoading={isSubmitting} type="submit">
            Sign in
          </Button>
        </form>
        <div className="mt-6 flex flex-wrap gap-x-4 gap-y-2 text-sm text-muted">
          {role === "hospital_admin" ? (
            <Link className="text-secondary hover:underline" to="/register">
              Register a hospital
            </Link>
          ) : null}
          <Link
            className="hover:text-ink hover:underline"
            to={role === "doctor" ? "/hospital-login" : "/doctor-login"}
          >
            Use {role === "doctor" ? "hospital administrator" : "doctor"} login
          </Link>
        </div>
      </Card>
    </AuthLayout>
  );
}

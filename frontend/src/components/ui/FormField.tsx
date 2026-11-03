import type { InputHTMLAttributes } from "react";

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function FormField({
  error,
  hint,
  id,
  label,
  required,
  ...inputProps
}: FormFieldProps) {
  const fieldId = id ?? label.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-");
  return (
    <label className="grid gap-2" htmlFor={fieldId}>
      <span className="text-sm font-medium text-ink">
        {label}
        {required ? <span className="ml-1 text-rose-300">*</span> : null}
      </span>
      <input
        {...inputProps}
        aria-describedby={error || hint ? `${fieldId}-description` : undefined}
        aria-invalid={Boolean(error)}
        className="min-h-11 rounded-lg border border-border bg-slate-900/40 px-3 text-ink outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/30"
        id={fieldId}
        required={required}
      />
      {error || hint ? (
        <span
          className={error ? "text-sm text-rose-300" : "text-sm text-muted"}
          id={`${fieldId}-description`}
        >
          {error ?? hint}
        </span>
      ) : null}
    </label>
  );
}

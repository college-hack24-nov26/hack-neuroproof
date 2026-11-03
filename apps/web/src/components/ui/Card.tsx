import type { HTMLAttributes, PropsWithChildren } from "react";

export function Card({
  children,
  className = "",
  ...props
}: PropsWithChildren<HTMLAttributes<HTMLElement>>) {
  return (
    <section
      {...props}
      className={`rounded-xl border border-border bg-surface p-5 shadow-card ${className}`}
    >
      {children}
    </section>
  );
}

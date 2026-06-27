import Link from "next/link";
import type { ReactNode } from "react";

type AuthFormShellProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer: ReactNode;
};

export function AuthFormShell({ title, subtitle, children, footer }: AuthFormShellProps) {
  return (
    <section className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-12">
      <Link href="/" className="mb-8 text-sm font-medium text-teal-700">
        Secure Job Platform
      </Link>
      <div className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold text-zinc-950">{title}</h1>
          {subtitle ? <p className="text-sm leading-6 text-zinc-600">{subtitle}</p> : null}
        </div>
        <div className="mt-6">{children}</div>
      </div>
      <div className="mt-5 text-center text-sm text-zinc-600">{footer}</div>
    </section>
  );
}

import Link from "next/link";
import { Suspense } from "react";
import { AuthFormShell } from "@/components/AuthFormShell";
import { LoginForm } from "@/components/LoginForm";

export default function LoginPage() {
  return (
    <AuthFormShell
      title="Sign in"
      footer={
        <>
          <Link className="font-medium text-teal-700" href="/forgot-password">
            Reset password
          </Link>
          <span className="px-2 text-zinc-300">|</span>
          <Link className="font-medium text-teal-700" href="/register">
            Create account
          </Link>
        </>
      }
    >
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthFormShell>
  );
}

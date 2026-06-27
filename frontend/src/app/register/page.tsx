import Link from "next/link";
import { AuthFormShell } from "@/components/AuthFormShell";
import { RegisterForm } from "@/components/RegisterForm";

export default function RegisterPage() {
  return (
    <AuthFormShell
      title="Create account"
      subtitle="Use a strong password with at least 12 characters."
      footer={
        <>
          Already registered?{" "}
          <Link className="font-medium text-teal-700" href="/login">
            Sign in
          </Link>
        </>
      }
    >
      <RegisterForm />
    </AuthFormShell>
  );
}

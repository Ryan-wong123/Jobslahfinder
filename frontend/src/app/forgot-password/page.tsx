import Link from "next/link";
import { AuthFormShell } from "@/components/AuthFormShell";
import { PasswordResetRequestForm } from "@/components/PasswordResetRequestForm";

export default function ForgotPasswordPage() {
  return (
    <AuthFormShell
      title="Reset password"
      footer={
        <>
          Have a token?{" "}
          <Link className="font-medium text-teal-700" href="/reset-password">
            Set new password
          </Link>
        </>
      }
    >
      <PasswordResetRequestForm />
    </AuthFormShell>
  );
}

import Link from "next/link";
import { AuthFormShell } from "@/components/AuthFormShell";
import { PasswordResetConfirmForm } from "@/components/PasswordResetConfirmForm";

export default function ResetPasswordPage() {
  return (
    <AuthFormShell
      title="Set new password"
      footer={
        <Link className="font-medium text-teal-700" href="/login">
          Return to sign in
        </Link>
      }
    >
      <PasswordResetConfirmForm />
    </AuthFormShell>
  );
}

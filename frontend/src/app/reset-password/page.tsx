import Link from "next/link";
import { AuthFormShell } from "@/components/AuthFormShell";
import { PasswordResetConfirmForm } from "@/components/PasswordResetConfirmForm";

type ResetPasswordPageProps = {
  searchParams?: Promise<{
    token?: string | string[];
  }>;
};

export default async function ResetPasswordPage({ searchParams }: ResetPasswordPageProps) {
  const params = await searchParams;
  const token = Array.isArray(params?.token) ? params.token[0] : params?.token ?? "";

  return (
    <AuthFormShell
      title="Set new password"
      footer={
        <Link className="font-medium text-teal-700" href="/login">
          Return to sign in
        </Link>
      }
    >
      <PasswordResetConfirmForm initialToken={token} />
    </AuthFormShell>
  );
}
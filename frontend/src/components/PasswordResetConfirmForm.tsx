"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function PasswordResetConfirmForm({ initialToken = "" }: { initialToken?: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const submittedToken = initialToken || String(formData.get("token") ?? "");
    const newPassword = String(formData.get("new_password") ?? "");

    if (!/^[A-Za-z0-9_-]{43}$/.test(submittedToken)) {
      setError("Reset token format is invalid. Please request a new reset link.");
      return;
    }
    if (newPassword.length < 12 || newPassword.length > 128 || !/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError("Password must be 12-128 characters and include uppercase, lowercase, and a number.");
      return;
    }

    setPending(true);
    setMessage(null);
    setError(null);

    try {
      const response = await apiFetch<{ message: string }>("/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({
          token: submittedToken,
          new_password: newPassword
        })
      });

      setMessage(response.message);
      form.reset();
      router.push("/login?password_reset=success");
    } catch {
      setError("Unable to reset password. Please request a new reset link and try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-4" method="post" onSubmit={onSubmit}>
      <FormMessage message={message} tone="success" />
      <FormMessage message={error} tone="error" />

      {initialToken ? (
        <input type="hidden" name="token" value={initialToken} />
      ) : (
        <TextField
          label="Reset token"
          name="token"
          autoComplete="one-time-code"
          minLength={43}
          maxLength={43}
          pattern="[A-Za-z0-9_-]{43}"
        />
      )}

      <TextField
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        maxLength={128}
        pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{12,128}"
        title="Use 12-128 characters with uppercase, lowercase, and a number."
      />
      <SubmitButton pending={pending}>Reset password</SubmitButton>
    </form>
  );
}

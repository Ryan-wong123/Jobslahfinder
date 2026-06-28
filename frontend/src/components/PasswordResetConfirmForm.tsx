"use client";

import { useState, type FormEvent } from "react";
import { apiFetch } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function PasswordResetConfirmForm() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setPending(true);
    setMessage(null);
    setError(null);

    const formData = new FormData(form);
    try {
      const response = await apiFetch<{ message: string }>("/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({
          token: formData.get("token"),
          new_password: formData.get("new_password")
        })
      });
      setMessage(response.message);
      form.reset();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reset password.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <FormMessage message={message} tone="success" />
      <FormMessage message={error} tone="error" />
      <TextField label="Reset token" name="token" autoComplete="one-time-code" />
      <TextField
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
      />
      <SubmitButton pending={pending}>Reset password</SubmitButton>
    </form>
  );
}

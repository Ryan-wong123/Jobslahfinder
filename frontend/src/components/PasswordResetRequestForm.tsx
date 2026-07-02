"use client";

import { useState, type FormEvent } from "react";
import { apiFetch } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function PasswordResetRequestForm() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = String(formData.get("email") ?? "").trim();
    if (!email || email.length > 255 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError("Enter a valid email address.");
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);

    try {
      const response = await apiFetch<{ message: string }>("/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email })
      });
      setMessage(response.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to request password reset.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <FormMessage message={message} tone="success" />
      <FormMessage message={error} tone="error" />
      <TextField label="Email" name="email" type="email" autoComplete="email" maxLength={255} />
      <SubmitButton pending={pending}>Request reset</SubmitButton>
    </form>
  );
}

"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiFetch, type LoginResponse } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const registered = searchParams.get("registered") === "1";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);

    const formData = new FormData(event.currentTarget);
    try {
      const response = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: formData.get("email"),
          password: formData.get("password")
        })
      });
      if (response.requires_2fa && response.challenge_token) {
        router.push(`/two-factor/verify?token=${encodeURIComponent(response.challenge_token)}`);
        return;
      }
      router.push("/account");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid email or password.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <FormMessage
        message={registered ? "Account created. Sign in to continue." : null}
        tone="success"
      />
      <FormMessage message={error} tone="error" />
      <TextField label="Email" name="email" type="email" autoComplete="email" />
      <TextField
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
      />
      <SubmitButton pending={pending}>Sign in</SubmitButton>
    </form>
  );
}

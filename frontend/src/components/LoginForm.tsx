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
  const passwordReset = searchParams.get("password_reset") === "success";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    if (!email || email.length > 255 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || password.length < 1 || password.length > 128) {
      setError("Invalid email or password.");
      return;
    }
    setPending(true);
    setError(null);

    try {
      const result = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email,
          password
        })
      });
      if (result.requires_2fa && result.challenge_token) {
        router.push(`/two-factor/verify?challenge=${encodeURIComponent(result.challenge_token)}`);
        return;
      }
      if (result.requires_2fa_setup) {
        router.push("/two-factor/setup");
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
        message={
          registered
            ? "Account created. Sign in to continue."
            : passwordReset
              ? "Password reset complete. Sign in with your new password."
              : null
        }
        tone="success"
      />
      <FormMessage message={error} tone="error" />
      <TextField label="Email" name="email" type="email" autoComplete="email" maxLength={255} />
      <TextField
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        maxLength={128}
      />
      <SubmitButton pending={pending}>Sign in</SubmitButton>
    </form>
  );
}
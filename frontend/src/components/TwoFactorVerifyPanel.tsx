"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiFetch } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function TwoFactorVerifyPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const challenge = searchParams.get("challenge");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const formData = new FormData(event.currentTarget);
    try {
      await apiFetch<{ message: string }>("/auth/2fa/verify", {
        method: "POST",
        body: JSON.stringify({
          challenge_token: challenge,
          code: formData.get("code")
        })
      });
      router.push("/account");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid verification code.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-6 py-12">
      <h1 className="text-2xl font-semibold text-zinc-950">Two-factor verification</h1>
      <p className="mt-3 text-sm text-zinc-700">Enter the six-digit code from Microsoft Authenticator.</p>
      <FormMessage message={!challenge ? "Missing verification challenge. Sign in again." : error} tone="error" />
      <form className="mt-6 space-y-4 rounded border border-zinc-200 bg-white p-5" onSubmit={onSubmit}>
        <TextField label="Verification code" name="code" inputMode="numeric" autoComplete="one-time-code" />
        <SubmitButton pending={pending || !challenge}>Verify and continue</SubmitButton>
      </form>
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiFetch } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

type TwoFactorVerifyPanelProps = {
  challengeToken: string;
};

export function TwoFactorVerifyPanel({ challengeToken }: TwoFactorVerifyPanelProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challengeToken) {
      setError("Missing verification challenge. Sign in again.");
      return;
    }
    setPending(true);
    setError(null);
    const formData = new FormData(event.currentTarget);
    try {
      await apiFetch<{ message: string }>("/auth/2fa/verify", {
        method: "POST",
        body: JSON.stringify({
          challenge_token: challengeToken,
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
      <p className="mt-3 text-sm text-zinc-700">Enter the six-digit code from your authenticator app.</p>
      <FormMessage message={!challengeToken ? "Missing verification challenge. Sign in again." : error} tone="error" />
      <form className="mt-6 space-y-4 rounded border border-zinc-200 bg-white p-5 shadow-sm" onSubmit={onSubmit}>
        <TextField
          label="Verification code"
          name="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          minLength={6}
          maxLength={8}
        />
        <SubmitButton pending={pending || !challengeToken}>Verify and continue</SubmitButton>
      </form>
    </div>
  );
}

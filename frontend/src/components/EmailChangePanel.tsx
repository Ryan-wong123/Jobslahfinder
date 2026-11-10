"use client";

import { useEffect, useState, type FormEvent } from "react";
import { apiFetch } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function EmailChangePanel() {
  const [token, setToken] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("email_change_token");
    if (value) {
      setToken(value);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setPending(true); setMessage(null); setError(null);
    try {
      const result = await apiFetch<{ message: string }>(`/auth/email-change/${token ? "confirm" : "request"}`, {
        method: "POST",
        body: JSON.stringify(token ? { token } : {
          email: data.get("email"), current_password: data.get("current_password"), code: data.get("code")
        })
      });
      setMessage(result.message); form.reset();
      if (token) { setToken(""); window.location.assign("/login"); }
    } catch {
      setError("Unable to change email. Check your details or request a new verification link.");
    } finally { setPending(false); }
  }

  return <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
    <h2 className="text-lg font-semibold text-zinc-950">Email address</h2>
    <p className="mt-2 text-sm text-zinc-600">Verify your new address before it becomes your sign-in and recovery address. Sign in to this account before opening the verification link.</p>
    <form className="mt-5 space-y-4" method="post" onSubmit={submit}>
      <FormMessage message={message} tone="success" /><FormMessage message={error} tone="error" />
      {token ? <p>Confirm the email change you requested. All sessions will be signed out.</p> : <>
        <TextField label="New email address" name="email" type="email" autoComplete="email" required />
        <TextField label="Current password" name="current_password" type="password" autoComplete="current-password" required />
        <TextField label="Authenticator code" name="code" type="text" autoComplete="one-time-code" required />
      </>}
      <SubmitButton pending={pending}>{token ? "Verify and change email" : "Send verification link"}</SubmitButton>
    </form>
  </section>;
}

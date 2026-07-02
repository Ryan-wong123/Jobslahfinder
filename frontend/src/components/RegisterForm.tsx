"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, type User } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function RegisterForm() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    if (!email || email.length > 255 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 12 || password.length > 128 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
      setError("Password must be 12-128 characters and include uppercase, lowercase, and a number.");
      return;
    }
    setPending(true);
    setError(null);

    try {
      await apiFetch<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password
        })
      });
      router.push("/login?registered=1");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to register account.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-4" method="post" onSubmit={onSubmit}>
      <FormMessage message={error} tone="error" />
      <TextField label="Email" name="email" type="email" autoComplete="email" maxLength={255} />
      <TextField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        maxLength={128}
        pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{12,128}"
        title="Use 12-128 characters with uppercase, lowercase, and a number."
      />
      <SubmitButton pending={pending}>Create account</SubmitButton>
    </form>
  );
}

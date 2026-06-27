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
    setPending(true);
    setError(null);

    const formData = new FormData(event.currentTarget);
    try {
      await apiFetch<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: formData.get("email"),
          password: formData.get("password")
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
    <form className="space-y-4" onSubmit={onSubmit}>
      <FormMessage message={error} tone="error" />
      <TextField label="Email" name="email" type="email" autoComplete="email" />
      <TextField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        minLength={12}
      />
      <SubmitButton pending={pending}>Create account</SubmitButton>
    </form>
  );
}

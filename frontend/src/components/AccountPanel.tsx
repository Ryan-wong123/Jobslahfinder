"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, formatDateTime, type User } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function AccountPanel() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingPassword, setPendingPassword] = useState(false);
  const [pendingLogout, setPendingLogout] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<User>("/me")
      .then((currentUser) => {
        if (active) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        router.replace("/login");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [router]);

  async function onPasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPendingPassword(true);
    setMessage(null);
    setError(null);

    const formData = new FormData(event.currentTarget);
    try {
      const response = await apiFetch<{ message: string }>("/auth/password-change", {
        method: "POST",
        body: JSON.stringify({
          current_password: formData.get("current_password"),
          new_password: formData.get("new_password")
        })
      });
      setMessage(response.message);
      event.currentTarget.reset();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to change password.");
    } finally {
      setPendingPassword(false);
    }
  }

  async function onLogout() {
    setPendingLogout(true);
    setError(null);
    try {
      await apiFetch<{ message: string }>("/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to log out.");
      setPendingLogout(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-600">Loading account...</p>;
  }

  if (!user) {
    return null;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-950">Account</h1>
            <p className="mt-1 text-sm text-zinc-600">{user.email}</p>
          </div>
          <span className="rounded border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-medium text-teal-800">
            {user.role}
          </span>
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="border-t border-zinc-200 pt-4">
            <dt className="text-xs font-medium uppercase text-zinc-500">Status</dt>
            <dd className="mt-1 text-sm text-zinc-950">{user.is_active ? "Active" : "Inactive"}</dd>
          </div>
          <div className="border-t border-zinc-200 pt-4">
            <dt className="text-xs font-medium uppercase text-zinc-500">Last login</dt>
            <dd className="mt-1 text-sm text-zinc-950">{formatDateTime(user.last_login_at)}</dd>
          </div>
          <div className="border-t border-zinc-200 pt-4">
            <dt className="text-xs font-medium uppercase text-zinc-500">Created</dt>
            <dd className="mt-1 text-sm text-zinc-950">{formatDateTime(user.created_at)}</dd>
          </div>
        </dl>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            className="rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-400"
            disabled={pendingLogout}
            onClick={onLogout}
            type="button"
          >
            {pendingLogout ? "Signing out..." : "Sign out"}
          </button>
          {user.role === "ADMIN" ? (
            <a
              className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
              href="/api/admin/health"
            >
              Admin health
            </a>
          ) : null}
        </div>
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Password</h2>
        <form className="mt-5 space-y-4" onSubmit={onPasswordChange}>
          <FormMessage message={message} tone="success" />
          <FormMessage message={error} tone="error" />
          <TextField
            label="Current password"
            name="current_password"
            type="password"
            autoComplete="current-password"
          />
          <TextField
            label="New password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            minLength={12}
          />
          <SubmitButton pending={pendingPassword}>Change password</SubmitButton>
        </form>
      </section>
    </div>
  );
}

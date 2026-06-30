"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDateTime, type AdminUserDetail } from "@/lib/api";

export function AdminUserDetailPanel() {
  const params = useParams<{ userId: string }>();
  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<AdminUserDetail>(`/admin/users/${params.userId}`)
      .then((response) => {
        if (active) {
          setUser(response);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load user details.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [params.userId]);

  if (loading) {
    return <p className="text-sm text-zinc-600">Loading user details...</p>;
  }

  if (error || !user) {
    return (
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-zinc-950">User Details</h1>
        <p className="mt-2 text-sm text-red-700">{error ?? "Unable to load user details."}</p>
        <Link className="mt-5 inline-block rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/admin">
          Back to admin
        </Link>
      </section>
    );
  }

  return (
    <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">User Details</h1>
          <p className="mt-1 text-sm text-zinc-600">{user.email}</p>
        </div>
        <Link className="rounded border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-900" href="/admin">
          Back
        </Link>
      </div>
      <dl className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Role</dt>
          <dd className="mt-2 text-zinc-950">{user.role}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Status</dt>
          <dd className="mt-2 text-zinc-950">{user.is_active ? "Active" : "Inactive"}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Last login</dt>
          <dd className="mt-2 text-zinc-950">{formatDateTime(user.last_login_at)}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Created</dt>
          <dd className="mt-2 text-zinc-950">{formatDateTime(user.created_at)}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Updated</dt>
          <dd className="mt-2 text-zinc-950">{formatDateTime(user.updated_at)}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Activity counts</dt>
          <dd className="mt-2 text-zinc-950">
            {user.resume_count} resumes, {user.saved_job_count} saved, {user.cover_letter_count} drafts
          </dd>
        </div>
      </dl>
    </section>
  );
}

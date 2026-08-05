"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, type User } from "@/lib/api";

const workspaces = [
  { label: "Jobs", value: "Browse", href: "/jobs" },
  { label: "Saved jobs", value: "Review", href: "/saved-jobs" },
  { label: "Resume", value: "Upload", href: "/resumes" },
  { label: "Recommendations", value: "Match", href: "/recommendations" },
  { label: "Roadmaps", value: "Plan", href: "/roadmaps" },
  { label: "Salary comparison", value: "Compare", href: "/salary-comparison" },
  { label: "Cover letters", value: "Draft", href: "/cover-letters" },
  { label: "History", value: "Track", href: "/application-history" }
];

export function HomeHub() {
  const [user, setUser] = useState<User | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch<User>("/me")
      .then((currentUser) => {
        if (active) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        if (active) {
          setUser(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 pb-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/status">
            Status
          </Link>
          {loaded && user ? (
            <Link className="rounded bg-zinc-950 px-3 py-2 font-medium text-white" href="/account">
              Account
            </Link>
          ) : (
            <>
              <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/login">
                Sign in
              </Link>
              <Link className="rounded bg-zinc-950 px-3 py-2 font-medium text-white" href="/register">
                Create account
              </Link>
            </>
          )}
        </nav>
      </header>

      <div className="grid flex-1 items-center gap-8 py-12 lg:grid-cols-[420px_1fr]">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-teal-700">
            ICT2216 Secure Software Development
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950">
            Secure Job Aggregation Platform
          </h1>
          <p className="mt-4 text-base leading-7 text-zinc-700">
            {user
              ? `Signed in as ${user.email}.`
              : "Create an account or sign in to access protected platform workflows."}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            {user ? (
              <Link className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/account">
                Open account
              </Link>
            ) : (
              <>
                <Link className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/register">
                  Create account
                </Link>
                <Link
                  className="rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900"
                  href="/login"
                >
                  Sign in
                </Link>
              </>
            )}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {workspaces.map((item) => (
            <a
              key={item.label}
              className="min-h-28 rounded border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-teal-700"
              href={item.href}
            >
              <p className="text-sm text-zinc-500">{item.label}</p>
              <p className="mt-2 text-2xl font-semibold text-zinc-950">{item.value}</p>
            </a>
          ))}
          {user?.role === "ADMIN" ? (
            <a
              className="min-h-28 rounded border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-teal-700"
              href="/admin"
            >
              <p className="text-sm text-zinc-500">Admin</p>
              <p className="mt-2 text-2xl font-semibold text-zinc-950">Scrape</p>
            </a>
          ) : null}
        </div>
      </div>
    </section>
  );
}

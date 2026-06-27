import Link from "next/link";
import { JobDetailPanel } from "@/components/JobDetailPanel";

export default function JobDetailPage() {
  return (
    <section className="mx-auto min-h-screen max-w-6xl px-6 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 pb-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/jobs">
            Jobs
          </Link>
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/saved-jobs">
            Saved
          </Link>
        </nav>
      </header>
      <JobDetailPanel />
    </section>
  );
}

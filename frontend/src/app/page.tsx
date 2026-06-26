import Link from "next/link";

const foundations = [
  "Authentication and RBAC",
  "Secure resume upload",
  "Approved-source scraping",
  "Audit logging",
  "Safe AI draft workflows"
];

export default function HomePage() {
  return (
    <section className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-12">
      <div className="space-y-6">
        <p className="text-sm font-medium uppercase tracking-wide text-teal-700">
          ICT2216 Secure Software Development
        </p>
        <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-zinc-950">
          Secure Job Aggregation Platform
        </h1>
        <p className="max-w-2xl text-base leading-7 text-zinc-700">
          Baseline project skeleton for the job search, resume processing,
          recommendation, cover letter, and admin monitoring workflows.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {foundations.map((item) => (
            <div key={item} className="rounded border border-zinc-200 bg-white p-4 text-sm text-zinc-700">
              {item}
            </div>
          ))}
        </div>
        <Link
          className="inline-flex rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white"
          href="/status"
        >
          View status
        </Link>
      </div>
    </section>
  );
}

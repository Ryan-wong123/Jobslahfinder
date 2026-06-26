import { getApiBaseUrl } from "@/lib/api";

export default function StatusPage() {
  return (
    <section className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold text-zinc-950">Platform Status</h1>
      <dl className="mt-6 grid gap-4 sm:grid-cols-2">
        <div className="rounded border border-zinc-200 bg-white p-4">
          <dt className="text-sm text-zinc-500">Frontend</dt>
          <dd className="mt-1 text-base font-medium text-zinc-900">Ready</dd>
        </div>
        <div className="rounded border border-zinc-200 bg-white p-4">
          <dt className="text-sm text-zinc-500">Backend API base</dt>
          <dd className="mt-1 break-all text-base font-medium text-zinc-900">{getApiBaseUrl()}</dd>
        </div>
      </dl>
    </section>
  );
}

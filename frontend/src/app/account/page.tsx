import Link from "next/link";
import { AccountPanel } from "@/components/AccountPanel";

export default function AccountPage() {
  return (
    <section className="mx-auto min-h-screen max-w-6xl px-6 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 pb-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <Link className="rounded px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-100" href="/">
          Home
        </Link>
      </header>
      <AccountPanel />
    </section>
  );
}

import Link from "next/link";
import { TwoFactorSetupPanel } from "@/components/TwoFactorSetupPanel";

export default function TwoFactorSetupPage() {
  return (
    <section className="min-h-screen bg-zinc-50">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <Link className="rounded px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-100" href="/account">
          Account
        </Link>
      </header>
      <TwoFactorSetupPanel />
    </section>
  );
}

import Link from "next/link";
import { TwoFactorVerifyPanel } from "@/components/TwoFactorVerifyPanel";

type TwoFactorVerifyPageProps = {
  searchParams: Promise<{ token?: string }>;
};

export default async function TwoFactorVerifyPage({ searchParams }: TwoFactorVerifyPageProps) {
  const { token = "" } = await searchParams;

  return (
    <section className="min-h-screen bg-zinc-50">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <Link className="rounded px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-100" href="/login">
          Sign in
        </Link>
      </header>
      <TwoFactorVerifyPanel challengeToken={token} />
    </section>
  );
}

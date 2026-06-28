import Link from "next/link";
import { ExtractedProfilePanel } from "@/components/ExtractedProfilePanel";

export default async function ExtractedProfilePage({ params }: { params: Promise<{ resumeId: string }> }) {
  const { resumeId: resumeIdParam } = await params;
  const resumeId = Number(resumeIdParam);
  return (
    <section className="mx-auto min-h-screen max-w-6xl px-6 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 pb-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href={`/resumes/${resumeId}`}>
            Resume
          </Link>
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/resumes">
            Resumes
          </Link>
        </nav>
      </header>
      <ExtractedProfilePanel resumeId={resumeId} editing={false} />
    </section>
  );
}

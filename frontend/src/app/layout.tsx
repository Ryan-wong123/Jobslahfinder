import type { Metadata } from "next";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "Secure Job Platform",
  description: "Secure AI-assisted job aggregation and application support platform"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <main className="min-h-screen bg-zinc-50 text-zinc-950">{children}</main>
      </body>
    </html>
  );
}

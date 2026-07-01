"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { apiFetch, type TwoFactorSetup } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

export function TwoFactorSetupPanel() {
  const router = useRouter();
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<TwoFactorSetup>("/auth/2fa/setup")
      .then(async (currentSetup) => {
        const qrCode = await QRCode.toDataURL(currentSetup.provisioning_uri, {
          errorCorrectionLevel: "M",
          margin: 2,
          scale: 6
        });
        if (active) {
          setSetup(currentSetup);
          setQrCodeUrl(qrCode);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to start setup.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const formData = new FormData(event.currentTarget);
    try {
      await apiFetch<{ message: string }>("/auth/2fa/confirm", {
        method: "POST",
        body: JSON.stringify({ code: formData.get("code") })
      });
      router.push("/account");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid verification code.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-6 py-12">
      <h1 className="text-2xl font-semibold text-zinc-950">Set up two-factor authentication</h1>
      <p className="mt-3 text-sm text-zinc-700">
        Add this account to your authenticator app, then enter the six-digit code.
      </p>
      <FormMessage message={error} tone="error" />
      {setup ? (
        <div className="mt-6 space-y-4 rounded border border-zinc-200 bg-white p-5 shadow-sm">
          {qrCodeUrl ? (
            <div className="flex flex-col items-center rounded border border-zinc-200 bg-white p-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                alt="QR code for authenticator app setup"
                className="h-56 w-56"
                height={224}
                src={qrCodeUrl}
                width={224}
              />
            </div>
          ) : null}
          <div>
            <p className="text-sm font-medium text-zinc-800">Manual setup key</p>
            <p className="mt-2 break-all rounded bg-zinc-100 px-3 py-2 font-mono text-sm text-zinc-950">
              {setup.secret}
            </p>
          </div>
          <form className="space-y-4" onSubmit={onSubmit}>
            <TextField
              label="Verification code"
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              minLength={6}
              maxLength={8}
            />
            <SubmitButton pending={pending}>Enable two-factor authentication</SubmitButton>
          </form>
        </div>
      ) : null}
    </div>
  );
}

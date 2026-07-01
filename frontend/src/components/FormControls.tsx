"use client";

import type { InputHTMLAttributes } from "react";

type FieldProps = {
  label: string;
  name: string;
  type?: InputHTMLAttributes<HTMLInputElement>["type"];
  autoComplete?: string;
  inputMode?: InputHTMLAttributes<HTMLInputElement>["inputMode"];
  required?: boolean;
  minLength?: number;
  maxLength?: number;
};

export function TextField({
  label,
  name,
  type = "text",
  autoComplete,
  inputMode,
  required = true,
  minLength,
  maxLength
}: FieldProps) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-zinc-800">{label}</span>
      <input
        className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
        name={name}
        type={type}
        autoComplete={autoComplete}
        inputMode={inputMode}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
      />
    </label>
  );
}

export function SubmitButton({ children, pending }: { children: string; pending: boolean }) {
  return (
    <button
      className="inline-flex w-full items-center justify-center rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
      disabled={pending}
      type="submit"
    >
      {pending ? "Please wait..." : children}
    </button>
  );
}

export function FormMessage({
  message,
  tone
}: {
  message: string | null;
  tone: "success" | "error";
}) {
  if (!message) {
    return null;
  }
  const classes =
    tone === "success"
      ? "border-teal-200 bg-teal-50 text-teal-900"
      : "border-red-200 bg-red-50 text-red-900";
  return <p className={`rounded border px-3 py-2 text-sm ${classes}`}>{message}</p>;
}

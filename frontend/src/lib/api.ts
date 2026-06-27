export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
}

export type ApiError = {
  detail?: string;
};

export type User = {
  id: number;
  email: string;
  role: "USER" | "ADMIN";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};

export async function apiFetch<TResponse>(
  path: string,
  options: RequestInit = {}
): Promise<TResponse> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers,
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = (await response.json()) as ApiError;
      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      message = "Something went wrong. Please try again.";
    }
    throw new Error(message);
  }

  return (await response.json()) as TResponse;
}

export function formatDateTime(value: string | null): string {
  if (!value) {
    return "Not yet";
  }
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

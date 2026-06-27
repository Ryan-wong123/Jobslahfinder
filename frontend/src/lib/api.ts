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

export type JobSource = {
  id: number;
  source_name: "JobStreet" | "MyCareersFuture" | string;
};

export type JobSummary = {
  id: number;
  title: string;
  company: string;
  location: string | null;
  category: string | null;
  source: JobSource;
  posting_date: string | null;
  scraped_at: string;
  is_active: boolean;
  is_suspicious: boolean;
  application_url_is_valid: boolean;
};

export type JobDetail = JobSummary & {
  description: string | null;
  job_url: string;
  external_link_warning: string;
};

export type JobListResponse = {
  items: JobSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type SavedJob = {
  job: JobSummary;
  saved_at: string;
};

export type SavedJobListResponse = {
  items: SavedJob[];
  page: number;
  page_size: number;
  total: number;
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

export function formatDate(value: string | null): string {
  if (!value) {
    return "Not listed";
  }
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium"
  }).format(new Date(value));
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

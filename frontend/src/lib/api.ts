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

export type Resume = {
  id: number;
  original_filename: string;
  file_hash: string;
  mime_type: string;
  file_size_bytes: number;
  upload_status: "PENDING" | "STORED" | "REJECTED" | "DELETED" | string;
  uploaded_at: string;
};

export type ResumeListResponse = {
  items: Resume[];
  total: number;
};

export type ResumeExtraction = {
  id: number;
  resume_id: number;
  processing_status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | string;
  skills_json: Record<string, unknown> | null;
  experience_json: Record<string, unknown> | null;
  education_json: Record<string, unknown> | null;
  years_experience: number | null;
  processed_at: string | null;
};

export async function apiFetch<TResponse>(
  path: string,
  options: RequestInit = {}
): Promise<TResponse> {
  const headers = new Headers(options.headers);
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body && !isFormData && !headers.has("Content-Type")) {
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

export function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

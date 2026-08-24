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
  totp_enabled: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type LoginResponse = {
  message: string;
  requires_2fa: boolean;
  requires_2fa_setup: boolean;
  challenge_token: string | null;
};

export type TwoFactorSetup = {
  secret: string;
  provisioning_uri: string;
};

export type Profile = {
  user_id: number;
  full_name: string | null;
  phone: string | null;
  location: string | null;
  summary: string | null;
  skills: string[];
  created_at: string;
  updated_at: string;
};

export type JobSource = {
  id: number;
  source_name: "JobStreet" | "MyCareersFuture" | "JobsLah" | string;
};

export type AdminUserListResponse = {
  items: User[];
  page: number;
  page_size: number;
  total: number;
};

export type AdminUserDetail = User & {
  updated_at: string;
  resume_count: number;
  saved_job_count: number;
  recommendation_count: number;
  cover_letter_count: number;
  application_history_count: number;
};

export type AdminHealth = {
  status: string;
  service: string;
  access: string;
  timestamp: string | null;
  database: { status: string } | null;
  redis: { status: string } | null;
  worker: { status: string } | null;
};

export type AdminJobSource = JobSource & {
  base_url: string;
  is_enabled: boolean;
  created_at: string;
  job_count: number;
};

export type ScrapingRun = {
  id: number;
  source_id: number;
  started_at: string;
  completed_at: string | null;
  status: "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | string;
  jobs_retrieved: number;
  error_message: string | null;
};

export type AdminAuditLog = {
  id: number;
  user_id: number | null;
  event_type: string;
  target_type: string | null;
  target_id: number | null;
  outcome: "SUCCESS" | "FAILURE" | "DENIED" | string;
  details_json: Record<string, unknown> | null;
  created_at: string;
};

export type AdminAuditLogListResponse = {
  items: AdminAuditLog[];
  page: number;
  page_size: number;
  total: number;
};

export type JobSummary = {
  id: number;
  title: string;
  company: string;
  location: string | null;
  category: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  minimum_experience: string | null;
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

export type SalaryTrendPoint = {
  period: string;
  average_salary: number;
  sample_count: number;
};

export type SalaryTrendResponse = {
  role: string;
  currency: string;
  period: string;
  points: SalaryTrendPoint[];
  sample_size: number;
};

export type JobRoleSummary = {
  slug: string;
  name: string;
  tagline: string;
  category: string;
  job_count: number;
  typical_monthly_salary: number | null;
};

export type JobRoleListResponse = {
  items: JobRoleSummary[];
};

export type ExperienceSalaryBand = {
  key: string;
  label: string;
  years_label: string;
  median_monthly_salary: number | null;
  percentile_25: number | null;
  percentile_75: number | null;
  sample_count: number;
  difference_from_preceding_band: number | null;
  insufficient_data: boolean;
};

export type ExperienceSalaryComparison = {
  role_slug: string;
  role_name: string;
  location: string | null;
  currency: string;
  period: string;
  observation_start: string | null;
  observation_end: string | null;
  minimum_reliable_sample: number;
  disclaimer: string;
  bands: ExperienceSalaryBand[];
};

export type JobRoleDetail = JobRoleSummary & {
  overview: string;
  tasks: string[];
  how_to_become_intro: string;
  how_to_become_steps: string[];
  top_skills: string[];
  salary_points: SalaryTrendPoint[];
  latest_jobs: JobSummary[];
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

export type Recommendation = {
  id: number;
  job: JobSummary;
  resume_id: number | null;
  match_score: number;
  rank: number | null;
  rationale: string | null;
  metadata: Record<string, unknown> | null;
  generated_at: string;
};

export type RecommendationListResponse = {
  items: Recommendation[];
  page: number;
  page_size: number;
  total: number;
};

export type CoverLetter = {
  id: number;
  job: JobSummary;
  resume_id: number | null;
  generated_text: string;
  edited_text: string | null;
  version_no: number;
  created_at: string;
  updated_at: string;
};

export type CoverLetterListResponse = {
  items: CoverLetter[];
  page: number;
  page_size: number;
  total: number;
};

export type ApplicationHistoryAction =
  | "cover_letter_generated"
  | "cover_letter_edited"
  | "job_saved"
  | "job_unsaved"
  | "recommendations_refreshed"
  | string;

export type ApplicationHistoryItem = {
  id: number;
  job: JobSummary | null;
  cover_letter_id: number | null;
  action_type: ApplicationHistoryAction;
  action_time: string;
};

export type ApplicationHistoryListResponse = {
  items: ApplicationHistoryItem[];
  page: number;
  page_size: number;
  total: number;
};

export type JobRoleRoadmapMilestone = {
  month: number;
  title: string;
  focus: string;
  actions: string[];
  evidence: string[];
};

export type JobRoleRoadmap = {
  id: number;
  target_role: string;
  target_level: "ENTRY" | "JUNIOR" | "MID" | "SENIOR";
  timeline_months: number;
  current_skills: string[];
  milestones: JobRoleRoadmapMilestone[];
  notes: string | null;
  status: "ACTIVE" | "ARCHIVED";
  created_at: string;
  updated_at: string;
};

export type JobRoleRoadmapListResponse = {
  items: JobRoleRoadmap[];
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
  skills: string[];
  experience: Array<Record<string, unknown>>;
  education: Array<Record<string, unknown>>;
  years_experience: number | null;
  processed_at: string | null;
};

export type ResumeExtractionUpdate = {
  skills: string[];
  experience: Array<{ description?: string }>;
  education: Array<{ description?: string }>;
  years_experience: number | null;
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

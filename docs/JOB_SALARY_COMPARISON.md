# Job Salary Comparison

## Purpose

The salary comparison feature helps users compare monthly salary trends for a selected job role using salary data already stored with approved job postings. The user-facing page is available at `/salary-comparison`.

## User-visible behaviour

Users select or enter a job role and choose a period of 3, 6, 12, or 24 months. The page displays the average monthly salary and sample count for each posting month. If no qualifying data is available, the page explains that salary-bearing job postings are required instead of presenting an inferred value.

Role input is limited to 2–100 characters and common job-title punctuation. Month options are allowlisted. Requests use the existing rate-limited `GET /salary-trends` endpoint, and errors are shown without internal implementation details.

## Salary data rules

- Only active, non-suspicious job postings are included.
- A posting must have a supported monthly, yearly, or hourly salary period and at least one salary bound.
- Salary ranges are represented by their midpoint. Yearly and hourly values are normalized to an estimated monthly amount before aggregation.
- Results are grouped by posting month, returned in chronological order, and report their sample size.
- Stored titles and salary fields remain untrusted data and are returned through typed API responses; the frontend does not render them as HTML.

The result is an informational comparison derived from available postings, not a guarantee of compensation.

## ML-assisted role discovery

Role discovery uses `sentence-transformers` to create embeddings from normalized job-role text and scikit-learn's DBSCAN algorithm to identify dense groups without requiring a predetermined number of roles. The DBSCAN epsilon and minimum-sample thresholds are environment-configured and validated at application startup.

Discovery is disabled by default. Every generated role is a candidate only: it must remain unavailable to normal users until an authenticated administrator reviews and explicitly approves it. Enabling discovery must never disable this approval gate. Malformed, suspicious, or inactive postings must not be used as trusted role labels.

The relevant settings are:

- `ROLE_DISCOVERY_ENABLED`
- `ROLE_DISCOVERY_MODEL`
- `ROLE_DISCOVERY_DBSCAN_EPS`
- `ROLE_DISCOVERY_DBSCAN_MIN_SAMPLES`
- `ROLE_DISCOVERY_REQUIRE_ADMIN_APPROVAL`

`ROLE_DISCOVERY_REQUIRE_ADMIN_APPROVAL` is fail-closed and must be `true`; startup validation rejects configurations that attempt to bypass administrator approval.

## Operational and security considerations

- Model execution belongs in a resource-limited background worker rather than a web request.
- Administrators must retain existing backend RBAC checks for review actions; hiding controls in the frontend is insufficient.
- Candidate creation and approval decisions should be audit logged without embedding full scraped descriptions or sensitive user data.
- Model names and clustering parameters are deployment configuration, not client-controlled input.
- Salary comparison does not require resume content and must not send personal data to the embedding model.

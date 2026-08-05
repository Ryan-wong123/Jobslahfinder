# Job Salary Comparison

## Purpose

The salary comparison feature helps users compare monthly salary signals for a selected job role using normalized salary data from active, non-suspicious job postings stored by the platform. It is available at `/salary-comparison`; the existing `/salary-trends` route remains available for compatibility.

## User-visible behaviour

Users select or enter a job role and choose a three, six, twelve, or twenty-four month period. The page displays the average monthly salary and sample count for each posting month. If no qualifying salary records exist, the page explains that there is not yet enough stored salary data. Role and period inputs are validated in the browser and again by the existing backend salary-trends endpoint.

Salary figures are indicative rather than guarantees. Results depend on salary ranges supplied by approved job sources and should be interpreted with the displayed sample size.

## Data handling and security

- Only active, non-suspicious postings are included.
- Salary ranges are normalized to monthly SGD values before aggregation.
- Role input and date-range choices are length- and allowlist-validated.
- Scraped titles and salary data remain untrusted and are rendered as text, not HTML.
- The read-only endpoint is rate limited to reduce resource-exhaustion risk.
- No resume, profile, or other user-owned data is needed for salary comparison.

## ML-assisted role discovery

Role discovery is designed to encode normalized job titles with `sentence-transformers` and group similar titles with scikit-learn's DBSCAN implementation. Runtime settings select the embedding model, DBSCAN epsilon, minimum cluster size, and maximum jobs processed in one run.

DBSCAN is used because it does not require a predetermined number of job-role clusters and can classify isolated titles as noise. Job postings supplied to discovery must remain limited to active, non-suspicious records, and processing should run outside request handling because model loading and inference are resource intensive.

Every machine-discovered role is a proposal. It must default to an unapproved state and must not be returned by user-facing role, roadmap, or salary-comparison APIs until an authenticated administrator explicitly approves it. Approval and rejection actions must be enforced by the backend and audit logged. Model output must never directly create a publicly visible role.

This issue adds the required ML dependencies and validated runtime configuration. The administrative proposal persistence and approval workflow described above remains a prerequisite before ML discovery can replace or extend the currently visible role catalogue.

## Configuration

| Environment variable | Purpose | Default example |
|---|---|---|
| `ROLE_DISCOVERY_MODEL` | Sentence-transformers model identifier | `sentence-transformers/all-MiniLM-L6-v2` |
| `ROLE_DISCOVERY_DBSCAN_EPS` | Maximum DBSCAN neighbourhood distance | `0.35` |
| `ROLE_DISCOVERY_DBSCAN_MIN_SAMPLES` | Minimum samples forming a dense region | `3` |
| `ROLE_DISCOVERY_MAX_JOBS` | Maximum postings considered per discovery run | `1000` |

Values are bounded by backend configuration validation to avoid invalid clustering parameters and unexpectedly large workloads.

// Mirrors backend/app/schemas.py. Keep in sync with docs/API_REFERENCE.md.

export type Role = "owner" | "editor" | "viewer";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS";
export type BodyType = "none" | "json" | "text" | "form";
export type AuthType = "none" | "bearer" | "basic" | "api_key_header" | "api_key_query";
export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type ResultStatus = "passed" | "failed" | "error";
export type Verdict = "pass" | "warn" | "fail" | "no_baseline";

export interface User { id: number; email: string; full_name: string; created_at: string }
export interface TokenResponse { access_token: string; token_type: string; user: User }

export interface RunBrief {
  id: number; status: RunStatus; total: number; passed: number; failed: number; errored: number;
  created_at: string; finished_at: string | null; regression_summary: RegressionSummary | null;
}

export interface Project {
  id: number; name: string; description: string; base_url: string; default_timeout_s: number;
  variables: Record<string, string>; role: Role; created_at: string;
  test_case_count: number; endpoint_count: number; collection_count: number; run_count: number;
  last_run: RunBrief | null;
}
export interface ProjectInput { name: string; description?: string; base_url?: string; default_timeout_s?: number; variables?: Record<string, string> }

export interface Member { user_id: number; email: string; full_name: string; role: Role }

export interface Endpoint { id: number; project_id: number; name: string; method: HttpMethod; path: string; description: string; source: string; created_at: string }
export interface EndpointInput { name: string; method: HttpMethod; path: string; description?: string }

export interface Collection { id: number; project_id: number; name: string; description: string; created_at: string; test_case_count: number }

export type AssertionType = "json_path" | "header" | "body_contains" | "response_time";
export interface Assertion { type: AssertionType; path?: string; name?: string; operator?: string; value?: unknown; max_ms?: number }

export interface TestCase {
  id: number; project_id: number; collection_id: number | null; endpoint_id: number | null;
  name: string; method: HttpMethod; path: string; headers: Record<string, string>; query_params: Record<string, string>;
  body_type: BodyType; body: unknown; auth_type: AuthType; auth_config: Record<string, string>;
  expected_status: number; assertions: Assertion[]; timeout_s: number | null; follow_redirects: boolean; enabled: boolean;
  created_at: string; updated_at: string; last_status: ResultStatus | null; last_response_time_ms: number | null;
}
export type TestCaseInput = Omit<TestCase, "id" | "project_id" | "created_at" | "updated_at" | "last_status" | "last_response_time_ms">;

export interface AssertionOutcome { type: string; description: string; passed: boolean; expected: unknown; actual: unknown; message: string }
export interface ExecuteResult {
  status: ResultStatus; status_code: number | null; response_time_ms: number | null; response_size: number | null;
  error_type: string | null; error: string | null; url: string; assertion_results: AssertionOutcome[];
  request_snapshot: { method?: string; url?: string; headers?: Record<string, string>; body?: string | null; redirects?: string[] };
  response_headers: Record<string, string>; response_body_preview: string | null;
}

export interface RegressionSummary {
  verdict: Verdict; new_failures: number; fixed: number; still_failing: number; still_passing: number; new_tests: number; performance_regressions: number;
}
export interface Run {
  id: number; project_id: number; project_name: string | null; collection_id: number | null; collection_name: string | null;
  schedule_id: number | null; trigger: "manual" | "schedule" | "ci"; label: string; status: RunStatus; concurrency: number;
  total: number; passed: number; failed: number; errored: number; progress: number; error_message: string | null;
  baseline_run_id: number | null; regression_summary: RegressionSummary | null;
  created_at: string; started_at: string | null; finished_at: string | null; duration_ms: number | null;
}
export interface Result extends ExecuteResult {
  id: number; run_id: number; test_case_id: number | null; test_name: string; method: string; created_at: string;
}
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }

export interface PerformanceCheck {
  state: "normal" | "regressed" | "insufficient_data"; samples: number; baseline_median_ms?: number; mad_ms?: number;
  threshold_ms?: number; current_ms?: number; change_pct?: number | null;
}
export interface RegressionEntry {
  test_case_id: number | null; test_name: string; method: string; url: string;
  change: "new_failure" | "fixed" | "still_failing" | "still_passing" | "new_test";
  status: ResultStatus; baseline_status: ResultStatus | null; status_code: number | null; baseline_status_code: number | null;
  response_time_ms: number | null; error: string | null; performance: PerformanceCheck | null;
}
export interface RegressionReport {
  run_id: number; baseline_run_id: number | null; verdict: Verdict; summary: Omit<RegressionSummary, "verdict">;
  new_failures: RegressionEntry[]; fixed: RegressionEntry[]; still_failing: RegressionEntry[]; new_tests: RegressionEntry[];
  performance_regressions: RegressionEntry[];
  thresholds: { history_window: number; min_samples: number; slowdown_ratio: number; min_delta_ms: number };
}

export interface Schedule {
  id: number; project_id: number; collection_id: number | null; collection_name: string | null; name: string; cron: string;
  enabled: boolean; concurrency: number; last_run_at: string | null; next_run_at: string | null; upcoming: string[]; created_at: string;
}
export interface CronPreview { valid: boolean; message: string | null; upcoming: string[] }

export interface ApiKey { id: number; name: string; prefix: string; revoked: boolean; created_at: string; last_used_at: string | null }
export interface ApiKeyCreated extends ApiKey { key: string }

export interface ImportResult {
  title: string; servers: string[]; endpoints_created: number; endpoints_skipped: number;
  test_cases_created: number; test_cases_skipped: number; collection_id: number | null; base_url_updated: boolean;
}

export interface TrendPoint {
  run_id: number; created_at: string; total: number; passed: number; failed: number; errored: number;
  pass_rate: number | null; avg_response_ms: number | null; verdict: Verdict | null; trigger: string;
}
export interface Analytics {
  totals: { test_cases: number; endpoints: number; collections: number; schedules: number; runs: number };
  overall: { window_runs: number; executions: number; pass_rate: number | null; avg_response_ms: number | null; regressions_detected: number };
  trend: TrendPoint[];
  slowest: { test_case_id: number; name: string; avg_ms: number; max_ms: number; samples: number }[];
  flaky: { test_case_id: number; name: string; flips: number; runs: number; pass_rate: number | null }[];
}
export interface Dashboard {
  projects: number; test_cases: number; active_runs: number; runs_14d: number; pass_rate_14d: number | null; avg_response_ms_14d: number | null;
  recent_runs: Run[];
  alerts: { run_id: number; project_id: number; project_name: string; verdict: Verdict; new_failures: number; performance_regressions: number; created_at: string }[];
  daily: { date: string; runs: number; passed: number; failed: number }[];
}
export interface Health {
  status: "ok" | "degraded"; version: string; execution_mode: string; environment: string;
  checks: Record<string, string>; limits: Record<string, number>;
}

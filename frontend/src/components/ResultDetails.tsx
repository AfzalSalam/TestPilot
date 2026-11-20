import { AlertOctagon, Check, X } from "lucide-react";
import type { AssertionOutcome, ExecuteResult } from "@/api/types";
import { bytes, ms, prettyJson } from "@/lib/format";
import { Alert, Badge, CodeBlock, ResultBadge } from "./ui/ui";

const ERROR_HELP: Record<string, string> = {
  ssrf_blocked: "TestPilot refuses to call private, loopback or cloud-metadata addresses (SSRF protection). Use a publicly reachable URL, or ask an admin to allow-list the host.",
  timeout: "The API did not answer within the configured timeout. Raise the timeout in the test or project settings if this is expected.",
  connection_error: "The connection was refused or the host is unreachable from the worker.",
  response_too_large: "The response exceeded the maximum size TestPilot reads. Narrow the request (pagination, filters).",
  missing_variable: "A {{variable}} used by this test is not defined. Add it under Settings → Variables.",
  invalid_url: "The URL is malformed, uses an unsupported scheme, or the project has no base URL.",
};

function Outcome({ a }: { a: AssertionOutcome }) {
  return (
    <div className={`assertion ${a.passed ? "" : "fail"}`}>
      {a.passed ? <Check size={16} color="var(--success)" /> : <X size={16} color="var(--danger)" />}
      <div>
        <div style={{ fontWeight: 550 }}>{a.description}</div>
        {!a.passed && (
          <div className="mono dim" style={{ fontSize: 12, marginTop: 2 }}>
            expected <b>{String(a.expected)}</b> · got <b>{String(a.actual)}</b>{a.message && <> — {a.message}</>}
          </div>
        )}
      </div>
    </div>
  );
}

export function ResultDetails({ result }: { result: Pick<ExecuteResult, "status" | "status_code" | "response_time_ms" | "response_size" | "error_type" | "error" | "url" | "assertion_results" | "request_snapshot" | "response_headers" | "response_body_preview"> & { method?: string } }) {
  const req = result.request_snapshot ?? {};
  const reqHeaders = Object.entries(req.headers ?? {});
  const resHeaders = Object.entries(result.response_headers ?? {});
  const body = prettyJson(result.response_body_preview);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="row wrap">
        <ResultBadge status={result.status} />
        {result.status_code !== null && <Badge tone={result.status_code < 400 ? "success" : "danger"}>HTTP {result.status_code}</Badge>}
        <Badge>{ms(result.response_time_ms)}</Badge>
        <Badge>{bytes(result.response_size)}</Badge>
      </div>

      {result.error && (
        <Alert tone="warning" icon={AlertOctagon}>
          <b>{result.error_type?.replace(/_/g, " ") ?? "error"}</b>: {result.error}
          {result.error_type && ERROR_HELP[result.error_type] && <div style={{ marginTop: 4, opacity: 0.85 }}>{ERROR_HELP[result.error_type]}</div>}
        </Alert>
      )}

      {result.assertion_results.length > 0 && (
        <div className="stack sm">
          <div className="label">Assertions ({result.assertion_results.filter((a) => a.passed).length}/{result.assertion_results.length} passed)</div>
          {result.assertion_results.map((a, i) => <Outcome key={i} a={a} />)}
        </div>
      )}

      <div className="stack sm">
        <div className="label">Request</div>
        <div className="mono"><b>{req.method ?? result.method}</b> <span className="dim" style={{ wordBreak: "break-all" }}>{result.url}</span></div>
        {!!req.redirects?.length && <div className="faint" style={{ fontSize: 12.5 }}>Followed redirects: {req.redirects.join(" → ")}</div>}
        {reqHeaders.length > 0 && <CodeBlock copy={false}>{reqHeaders.map(([k, v]) => `${k}: ${v}`).join("\n")}</CodeBlock>}
        {req.body && <CodeBlock>{prettyJson(req.body)}</CodeBlock>}
        <div className="faint" style={{ fontSize: 12 }}>Credentials are redacted before storage.</div>
      </div>

      {result.status_code !== null && (
        <div className="stack sm">
          <div className="label">Response body {result.response_body_preview && result.response_size && result.response_size > result.response_body_preview.length ? "(preview)" : ""}</div>
          {body ? <CodeBlock>{body}</CodeBlock> : <span className="faint">Empty body</span>}
          {resHeaders.length > 0 && (
            <details><summary className="dim" style={{ cursor: "pointer", marginBottom: 8 }}>Response headers ({resHeaders.length})</summary>
              <CodeBlock copy={false}>{resHeaders.map(([k, v]) => `${k}: ${v}`).join("\n")}</CodeBlock></details>
          )}
        </div>
      )}
    </div>
  );
}

import { Plus, Save, Send, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError } from "@/api/client";
import { useCollections, useEndpoints, useTestCaseMutations } from "@/api/hooks";
import type { Assertion, AuthType, BodyType, ExecuteResult, HttpMethod, TestCase, TestCaseInput } from "@/api/types";
import { ResultDetails } from "./ResultDetails";
import { Drawer, useToast } from "./ui/overlays";
import { Alert, Button, Field, Input, KeyValueEditor, Segmented, Select, Switch, Textarea } from "./ui/ui";

const METHODS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
const OPERATORS: { value: string; label: string; noValue?: boolean }[] = [
  { value: "eq", label: "equals" }, { value: "neq", label: "does not equal" }, { value: "contains", label: "contains" }, { value: "not_contains", label: "does not contain" },
  { value: "exists", label: "exists", noValue: true }, { value: "not_exists", label: "does not exist", noValue: true },
  { value: "gt", label: ">" }, { value: "gte", label: "≥" }, { value: "lt", label: "<" }, { value: "lte", label: "≤" },
  { value: "regex", label: "matches regex" }, { value: "type", label: "has type" }, { value: "length", label: "has length" },
];
const AUTH_LABEL: Record<AuthType, string> = { none: "No authentication", bearer: "Bearer token", basic: "Basic auth", api_key_header: "API key (header)", api_key_query: "API key (query param)" };

const blank = (collectionId?: number | null): TestCaseInput => ({
  collection_id: collectionId ?? null, endpoint_id: null, name: "", method: "GET", path: "/", headers: {}, query_params: {}, body_type: "none", body: null,
  auth_type: "none", auth_config: {}, expected_status: 200, assertions: [], timeout_s: null, follow_redirects: true, enabled: true,
});

/** "42" → 42, "true" → true, '"x"' → "x", anything else stays a string. */
export function parseValue(text: string): unknown {
  const t = text.trim();
  if (t === "") return "";
  try { return JSON.parse(t); } catch { return text; }
}
export const valueToText = (v: unknown) => (v === undefined || v === null ? "" : typeof v === "string" ? v : JSON.stringify(v));

function AssertionRow({ a, onChange, onRemove }: { a: Assertion; onChange: (a: Assertion) => void; onRemove: () => void }) {
  const noValue = OPERATORS.find((o) => o.value === a.operator)?.noValue;
  const [valueText, setValueText] = useState(valueToText(a.value));
  const opSelect = (
    <Select className="sm" value={a.operator ?? "eq"} onChange={(e) => onChange({ ...a, operator: e.target.value })} aria-label="Operator" style={{ width: 150 }}>
      {OPERATORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </Select>
  );
  const valueInput = !noValue && (
    <Input className="sm" placeholder="expected value" value={valueText} aria-label="Expected value" style={{ minWidth: 120, flex: 1 }}
      onChange={(e) => { setValueText(e.target.value); onChange({ ...a, value: parseValue(e.target.value) }); }} />
  );
  return (
    <div className="card" style={{ padding: 10, background: "var(--bg-elev)" }}>
      <div className="row wrap">
        <span className="badge accent" style={{ minWidth: 92, justifyContent: "center" }}>{{ json_path: "JSON path", header: "Header", body_contains: "Body", response_time: "Time" }[a.type]}</span>
        {a.type === "json_path" && <><Input className="sm mono" placeholder="$.data.items[0].id" value={a.path ?? ""} onChange={(e) => onChange({ ...a, path: e.target.value })} aria-label="JSON path" style={{ flex: 1, minWidth: 140 }} />{opSelect}{valueInput}</>}
        {a.type === "header" && <><Input className="sm" placeholder="Content-Type" value={a.name ?? ""} onChange={(e) => onChange({ ...a, name: e.target.value })} aria-label="Header name" style={{ width: 160 }} />{opSelect}{valueInput}</>}
        {a.type === "body_contains" && <><span className="dim">contains</span><Input className="sm" placeholder="text that must appear" value={valueText} onChange={(e) => { setValueText(e.target.value); onChange({ ...a, value: e.target.value }); }} aria-label="Text" style={{ flex: 1 }} /></>}
        {a.type === "response_time" && <><span className="dim">under</span><Input className="sm" type="number" min={1} value={a.max_ms ?? 1000} onChange={(e) => onChange({ ...a, max_ms: Number(e.target.value) })} aria-label="Max milliseconds" style={{ width: 110 }} /><span className="dim">ms</span></>}
        <Button size="sm" variant="ghost" iconOnly icon={Trash2} onClick={onRemove} aria-label="Remove assertion" />
      </div>
    </div>
  );
}

export function TestCaseEditor({ projectId, existing, defaultCollectionId, onClose }: { projectId: number; existing?: TestCase; defaultCollectionId?: number | null; onClose: () => void }) {
  const toast = useToast();
  const { create, update, tryUnsaved } = useTestCaseMutations(projectId);
  const { data: collections } = useCollections(projectId);
  const { data: endpoints } = useEndpoints(projectId);

  const [form, setForm] = useState<TestCaseInput>(() => {
    if (!existing) return blank(defaultCollectionId);
    const { id: _id, project_id: _p, created_at: _c, updated_at: _u, last_status: _s, last_response_time_ms: _t, ...rest } = existing;
    void _id; void _p; void _c; void _u; void _s; void _t;
    return rest;
  });
  const [bodyText, setBodyText] = useState(() => (existing?.body_type === "json" || existing?.body_type === "text") ? (typeof existing.body === "string" ? existing.body : JSON.stringify(existing.body, null, 2)) : "");
  const [tab, setTab] = useState<"request" | "auth" | "assertions" | "settings">("request");
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const set = <K extends keyof TestCaseInput>(k: K, v: TestCaseInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  const payload = useMemo((): { data?: TestCaseInput; error?: string } => {
    let body: unknown = form.body;
    if (form.body_type === "json") {
      if (!bodyText.trim()) return { error: "JSON body is empty" };
      try { body = JSON.parse(bodyText); } catch (e) { return { error: `Body is not valid JSON: ${(e as Error).message}` }; }
    } else if (form.body_type === "text") body = bodyText;
    else if (form.body_type === "none") body = null;
    return { data: { ...form, body, name: form.name.trim() || "Untitled request" } };
  }, [form, bodyText]);

  const saving = create.isPending || update.isPending;
  const mutationError = (create.error ?? update.error ?? tryUnsaved.error) as Error | null;
  const fieldErrors = mutationError instanceof ApiError ? mutationError.fieldErrors : {};

  const send = () => {
    setLocalError(null);
    if (payload.error) return setLocalError(payload.error);
    tryUnsaved.mutate(payload.data!, { onSuccess: setResult });
  };
  const save = () => {
    setLocalError(null);
    if (!form.name.trim()) { setTab("request"); return setLocalError("Give the test a name"); }
    if (payload.error) return setLocalError(payload.error);
    const done = { onSuccess: () => { toast.success(existing ? "Test case saved" : "Test case created"); onClose(); } };
    if (existing) update.mutate({ id: existing.id, body: payload.data! }, done); else create.mutate(payload.data!, done);
  };

  const addAssertion = (a: Assertion) => set("assertions", [...form.assertions, a]);
  const bodyHint: Record<BodyType, string> = { none: "", json: "Sent as application/json", text: "Sent as text/plain", form: "Sent as application/x-www-form-urlencoded" };

  return (
    <Drawer title={existing ? `Edit: ${existing.name}` : "New test case"} onClose={onClose}
      footer={<><Button icon={Send} loading={tryUnsaved.isPending} onClick={send}>Send request</Button><div className="spacer" /><Button onClick={onClose}>Cancel</Button><Button variant="primary" icon={Save} loading={saving} onClick={save}>{existing ? "Save changes" : "Create test"}</Button></>}>
      <div className="stack" style={{ gap: 18 }}>
        {(localError || (mutationError && !Object.keys(fieldErrors).length)) && <Alert tone="danger">{localError ?? mutationError?.message}</Alert>}
        <Field label="Name" error={fieldErrors.name}><Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Get product by id returns 200" autoFocus /></Field>

        <div className="row" style={{ alignItems: "flex-start" }}>
          <Select value={form.method} onChange={(e) => set("method", e.target.value as HttpMethod)} style={{ width: 118 }} aria-label="HTTP method">{METHODS.map((m) => <option key={m}>{m}</option>)}</Select>
          <Input className="mono grow" value={form.path} onChange={(e) => set("path", e.target.value)} placeholder="/products/1  or  https://api.example.com/x" aria-label="Path or URL" />
        </div>

        <Segmented value={tab} onChange={setTab} options={[
          { value: "request", label: "Request" }, { value: "auth", label: "Auth" },
          { value: "assertions", label: `Assertions (${form.assertions.length + 1})` }, { value: "settings", label: "Settings" },
        ]} />

        {tab === "request" && (
          <div className="stack" style={{ gap: 20 }}>
            <Field label="Query parameters"><KeyValueEditor value={form.query_params} onChange={(v) => set("query_params", v)} keyPlaceholder="page" valuePlaceholder="1" /></Field>
            <Field label="Headers"><KeyValueEditor value={form.headers} onChange={(v) => set("headers", v)} keyPlaceholder="Accept" valuePlaceholder="application/json" /></Field>
            <Field label="Body" hint={bodyHint[form.body_type]}>
              <div className="stack sm">
                <Segmented value={form.body_type} onChange={(v) => { set("body_type", v); if (v === "form" && (typeof form.body !== "object" || form.body === null)) set("body", {}); }}
                  options={(["none", "json", "text", "form"] as BodyType[]).map((v) => ({ value: v, label: v === "none" ? "None" : v.toUpperCase() }))} />
                {form.body_type === "json" && <Textarea mono rows={9} value={bodyText} onChange={(e) => setBodyText(e.target.value)} placeholder={'{\n  "name": "Webcam",\n  "price": 59.9\n}'} spellCheck={false} aria-label="JSON body" />}
                {form.body_type === "text" && <Textarea mono rows={6} value={bodyText} onChange={(e) => setBodyText(e.target.value)} aria-label="Text body" />}
                {form.body_type === "form" && <KeyValueEditor value={(form.body as Record<string, string>) ?? {}} onChange={(v) => set("body", v)} />}
              </div>
            </Field>
          </div>
        )}

        {tab === "auth" && (
          <div className="stack">
            <Field label="Authentication type">
              <Select value={form.auth_type} onChange={(e) => setForm((f) => ({ ...f, auth_type: e.target.value as AuthType, auth_config: {} }))}>{(Object.keys(AUTH_LABEL) as AuthType[]).map((a) => <option key={a} value={a}>{AUTH_LABEL[a]}</option>)}</Select>
            </Field>
            {form.auth_type === "bearer" && <Field label="Token" hint="Sent as Authorization: Bearer …"><Input type="password" autoComplete="off" value={form.auth_config.token ?? ""} onChange={(e) => set("auth_config", { token: e.target.value })} placeholder="{{token}}" /></Field>}
            {form.auth_type === "basic" && <div className="form-grid"><Field label="Username"><Input value={form.auth_config.username ?? ""} onChange={(e) => set("auth_config", { ...form.auth_config, username: e.target.value })} /></Field><Field label="Password"><Input type="password" autoComplete="off" value={form.auth_config.password ?? ""} onChange={(e) => set("auth_config", { ...form.auth_config, password: e.target.value })} /></Field></div>}
            {(form.auth_type === "api_key_header" || form.auth_type === "api_key_query") && <div className="form-grid"><Field label={form.auth_type === "api_key_header" ? "Header name" : "Parameter name"}><Input value={form.auth_config.name ?? ""} onChange={(e) => set("auth_config", { ...form.auth_config, name: e.target.value })} placeholder={form.auth_type === "api_key_header" ? "X-API-Key" : "api_key"} /></Field><Field label="Value"><Input type="password" autoComplete="off" value={form.auth_config.value ?? ""} onChange={(e) => set("auth_config", { ...form.auth_config, value: e.target.value })} /></Field></div>}
            {form.auth_type !== "none" && <Alert tone="info">Credentials are encrypted at rest, never returned by the API (shown as ••••••••), and redacted in stored requests and logs. You can reference project variables like <span className="mono">{"{{token}}"}</span>.</Alert>}
          </div>
        )}

        {tab === "assertions" && (
          <div className="stack">
            <div className="card" style={{ padding: 12, background: "var(--bg-elev)" }}>
              <div className="row wrap"><span className="badge accent" style={{ minWidth: 92, justifyContent: "center" }}>Status</span><span className="dim">code equals</span>
                <Input className="sm" type="number" min={100} max={599} value={form.expected_status} onChange={(e) => set("expected_status", Number(e.target.value))} style={{ width: 90 }} aria-label="Expected status code" />
                {fieldErrors.expected_status && <span className="error-text">{fieldErrors.expected_status}</span>}</div>
            </div>
            {form.assertions.map((a, i) => <AssertionRow key={i} a={a} onChange={(n) => set("assertions", form.assertions.map((x, j) => (j === i ? n : x)))} onRemove={() => set("assertions", form.assertions.filter((_, j) => j !== i))} />)}
            <div className="row wrap">
              <Button size="sm" icon={Plus} onClick={() => addAssertion({ type: "json_path", path: "$.", operator: "eq", value: "" })}>JSON path</Button>
              <Button size="sm" icon={Plus} onClick={() => addAssertion({ type: "header", name: "Content-Type", operator: "contains", value: "json" })}>Header</Button>
              <Button size="sm" icon={Plus} onClick={() => addAssertion({ type: "body_contains", value: "" })}>Body contains</Button>
              <Button size="sm" icon={Plus} onClick={() => addAssertion({ type: "response_time", max_ms: 1000 })}>Response time</Button>
            </div>
            <p className="faint" style={{ fontSize: 12.5 }}>JSON paths support <span className="mono">$.a.b</span>, <span className="mono">$.items[0].id</span> and <span className="mono">$['key']</span>. Values like <span className="mono">42</span> or <span className="mono">true</span> are typed automatically.</p>
          </div>
        )}

        {tab === "settings" && (
          <div className="stack">
            <div className="form-grid">
              <Field label="Collection"><Select value={form.collection_id ?? ""} onChange={(e) => set("collection_id", e.target.value ? Number(e.target.value) : null)}><option value="">None</option>{collections?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
              <Field label="Linked endpoint"><Select value={form.endpoint_id ?? ""} onChange={(e) => set("endpoint_id", e.target.value ? Number(e.target.value) : null)}><option value="">None</option>{endpoints?.map((e) => <option key={e.id} value={e.id}>{e.method} {e.path}</option>)}</Select></Field>
              <Field label="Timeout (seconds)" hint="Empty = project default" error={fieldErrors.timeout_s}><Input type="number" min={0.5} max={60} step={0.5} value={form.timeout_s ?? ""} onChange={(e) => set("timeout_s", e.target.value ? Number(e.target.value) : null)} /></Field>
            </div>
            <Switch checked={form.follow_redirects} onChange={(v) => set("follow_redirects", v)} label="Follow redirects (each hop is re-validated against SSRF rules)" />
            <Switch checked={form.enabled} onChange={(v) => set("enabled", v)} label="Enabled (disabled tests are skipped by runs)" />
          </div>
        )}

        {result && (
          <div className="card" style={{ padding: 18, background: "var(--bg-elev)" }}>
            <div className="row between" style={{ marginBottom: 12 }}><h3>Response</h3><span className="faint" style={{ fontSize: 12.5 }}>Not saved to run history</span></div>
            <ResultDetails result={{ ...result, method: form.method }} />
          </div>
        )}
      </div>
    </Drawer>
  );
}

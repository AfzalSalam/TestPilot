import { CheckCircle2, FileUp, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useImportOpenApi } from "@/api/hooks";
import type { ImportResult } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { Alert, Button, Card, CardHeader, Switch, errorMessage } from "@/components/ui/ui";

export default function ImportPage() {
  const { projectId, canEdit } = useProjectCtx();
  const imp = useImportOpenApi(projectId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [tests, setTests] = useState(true);
  const [collection, setCollection] = useState(true);
  const [baseUrl, setBaseUrl] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (f: File) => {
    if (f.size > 5 * 1024 * 1024) return setError("File is larger than 5 MB.");
    setText(await f.text()); setFileName(f.name); setError(null); setResult(null);
  };
  const submit = () => {
    setError(null); setResult(null);
    imp.mutate({ spec_text: text, create_test_cases: tests, create_collection: collection, set_base_url: baseUrl }, { onSuccess: setResult, onError: (e) => setError(errorMessage(e)) });
  };

  if (!canEdit) return <Alert tone="info">You have view-only access. Ask an owner or editor to import a spec.</Alert>;

  return (
    <div className="grid-2" style={{ alignItems: "start" }}>
      <Card>
        <CardHeader title="OpenAPI / Swagger spec" />
        <div className="card-body stack">
          <div className="dropzone" role="button" tabIndex={0} onClick={() => fileRef.current?.click()} onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) void load(f); }}>
            <UploadCloud size={26} />
            <b>{fileName ?? "Drop a .json / .yaml file or click to browse"}</b>
            <span className="faint">OpenAPI 3.x or Swagger 2.0, up to 5 MB</span>
            <input ref={fileRef} type="file" hidden accept=".json,.yaml,.yml,application/json" onChange={(e) => { const f = e.target.files?.[0]; if (f) void load(f); e.target.value = ""; }} />
          </div>
          <textarea className="textarea mono" rows={10} placeholder="…or paste the spec here (JSON or YAML)" value={text} onChange={(e) => { setText(e.target.value); setFileName(null); }} />
          {error && <Alert tone="danger">{error}</Alert>}
          <Button variant="primary" icon={FileUp} loading={imp.isPending} disabled={!text.trim()} onClick={submit}>Import spec</Button>
        </div>
      </Card>
      <div className="stack">
        <Card>
          <CardHeader title="Options" />
          <div className="card-body stack">
            <Switch checked={tests} onChange={setTests} label="Generate a starter test for each operation (checks the documented success status)" />
            <Switch checked={collection} onChange={setCollection} label="Put generated tests in a new collection" disabled={!tests} />
            <Switch checked={baseUrl} onChange={setBaseUrl} label="Set the project base URL from the spec's first server (only if empty)" />
            <p className="faint" style={{ fontSize: 12.5 }}>Importing is safe to repeat: operations that already exist (same method and path) are skipped. Path parameters become <span className="mono">{"{{variables}}"}</span> you can define in Settings.</p>
          </div>
        </Card>
        {result && (
          <Card>
            <CardHeader title={<span className="row"><CheckCircle2 size={16} color="var(--success)" />Imported “{result.title}”</span>} />
            <div className="card-body stack sm">
              <div>Endpoints: <b>{result.endpoints_created}</b> created, {result.endpoints_skipped} skipped</div>
              <div>Test cases: <b>{result.test_cases_created}</b> created, {result.test_cases_skipped} skipped</div>
              {result.base_url_updated && <div>Base URL updated from spec.</div>}
              {result.servers.length > 0 && <div className="faint mono" style={{ fontSize: 12 }}>Servers: {result.servers.join(", ")}</div>}
              <div className="row"><Link to={`/projects/${projectId}/endpoints`}><Button size="sm">View endpoints</Button></Link><Link to={`/projects/${projectId}/tests`}><Button size="sm">View tests</Button></Link></div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

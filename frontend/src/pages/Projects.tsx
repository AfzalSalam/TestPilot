import { FlaskConical, FolderKanban, History, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useCreateProject, useProjects } from "@/api/hooks";
import type { Project } from "@/api/types";
import { Modal, useToast } from "@/components/ui/overlays";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, KeyValueEditor, PageHeader, RunStatusBadge, Skeleton, Textarea } from "@/components/ui/ui";
import { pct, plural, timeAgo } from "@/lib/format";

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const toast = useToast();
  const create = useCreateProject();
  const [form, setForm] = useState({ name: "", description: "", base_url: "", default_timeout_s: 10 });
  const [variables, setVariables] = useState<Record<string, string>>({});
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};

  const submit = () =>
    create.mutate({ ...form, variables }, {
      onSuccess: (p) => { toast.success("Project created", p.name); onClose(); nav(`/projects/${p.id}`); },
    });

  return (
    <Modal title="New project" onClose={onClose} wide footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} disabled={!form.name.trim()} onClick={submit}>Create project</Button></>}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {create.error && !Object.keys(fieldErrors).length && <Alert tone="danger">{(create.error as Error).message}</Alert>}
        <div className="form-grid">
          <Field label="Name" error={fieldErrors.name}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Payments API" autoFocus invalid={!!fieldErrors.name} /></Field>
          <Field label="Base URL" hint="Test paths are relative to this URL" error={fieldErrors.base_url}><Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.example.com" invalid={!!fieldErrors.base_url} /></Field>
          <Field label="Description" className="full"><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What does this API do?" /></Field>
          <Field label="Default timeout (seconds)" hint="Per request; individual tests can override" error={fieldErrors.default_timeout_s}>
            <Input type="number" min={0.5} max={60} step={0.5} value={form.default_timeout_s} onChange={(e) => setForm({ ...form, default_timeout_s: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Variables" hint={<>Reference as <span className="mono">{"{{name}}"}</span> in paths, headers, bodies and credentials. Stored encrypted.</> as unknown as string}>
          <KeyValueEditor value={variables} onChange={setVariables} keyPlaceholder="token" valuePlaceholder="value" secret />
        </Field>
      </form>
    </Modal>
  );
}

export function ProjectCard({ p }: { p: Project }) {
  const nav = useNavigate();
  const last = p.last_run;
  const rate = last && last.total ? Math.round((last.passed / last.total) * 100) : null;
  return (
    <Card className="project-card" onClick={() => nav(`/projects/${p.id}`)}>
      <div className="row between"><h3 className="truncate">{p.name}</h3><Badge tone={p.role === "owner" ? "accent" : undefined}>{p.role}</Badge></div>
      <p className="dim" style={{ minHeight: 40, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{p.description || "No description"}</p>
      {p.base_url ? <span className="url-chip truncate">{p.base_url}</span> : <span className="faint" style={{ fontSize: 12.5 }}>No base URL set</span>}
      <div className="meta">
        <span><FlaskConical size={14} />{plural(p.test_case_count, "test")}</span>
        <span><History size={14} />{plural(p.run_count, "run")}</span>
      </div>
      <div className="row between" style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        {last ? (<><div className="row"><RunStatusBadge status={last.status} /><span className="dim">{pct(rate)} passed</span></div><span className="faint">{timeAgo(last.finished_at ?? last.created_at)}</span></>) : <span className="faint">Never run</span>}
      </div>
    </Card>
  );
}

export default function ProjectsPage() {
  const { data, isLoading, error } = useProjects();
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState("");
  const filtered = useMemo(() => (data ?? []).filter((p) => (p.name + p.description).toLowerCase().includes(q.toLowerCase())), [data, q]);

  return (
    <div className="page">
      <PageHeader title="Projects" sub="Each project groups the APIs, tests and history for one service.">
        <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>New project</Button>
      </PageHeader>
      {error && <Alert tone="danger">{(error as Error).message}</Alert>}
      {isLoading ? <div className="grid-auto"><Skeleton h={220} /><Skeleton h={220} /><Skeleton h={220} /></div>
        : !data?.length ? <div className="card"><EmptyState icon={FolderKanban} title="Create your first project" action={<Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>New project</Button>}>A project holds the base URL, variables, test cases and run history of one API.</EmptyState></div>
        : (
          <div className="stack">
            {data.length > 4 && <div className="input-group" style={{ maxWidth: 320 }}><Search size={16} /><Input placeholder="Filter projects…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter projects" /></div>}
            <div className="grid-auto">{filtered.map((p) => <ProjectCard key={p.id} p={p} />)}</div>
          </div>
        )}
      {creating && <CreateProjectModal onClose={() => setCreating(false)} />}
    </div>
  );
}

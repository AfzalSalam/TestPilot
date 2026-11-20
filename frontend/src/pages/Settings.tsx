import { KeyRound, Plus, Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiKeyMutations, useApiKeys, useDeleteProject, useMemberMutations, useMembers, useUpdateProject } from "@/api/hooks";
import type { ApiKeyCreated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Alert, Badge, Button, Card, CardHeader, CodeBlock, EmptyState, Field, Input, KeyValueEditor, Select, errorMessage } from "@/components/ui/ui";
import { timeAgo } from "@/lib/format";

function General() {
  const { project, projectId, canEdit } = useProjectCtx();
  const toast = useToast();
  const update = useUpdateProject(projectId);
  const [f, setF] = useState({ name: project.name, description: project.description, base_url: project.base_url, default_timeout_s: project.default_timeout_s });
  const [vars, setVars] = useState<Record<string, string>>(project.variables);
  const [err, setErr] = useState<string | null>(null);
  const save = () => {
    setErr(null);
    const variables = Object.fromEntries(Object.entries(vars).filter(([k]) => k.trim()));
    update.mutate({ ...f, variables }, { onSuccess: () => toast.success("Settings saved"), onError: (e) => setErr(errorMessage(e)) });
  };
  return (
    <Card>
      <CardHeader title="General" />
      <div className="card-body stack">
        {err && <Alert tone="danger">{err}</Alert>}
        <div className="grid-2">
          <Field label="Name"><Input value={f.name} disabled={!canEdit} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Default timeout (seconds)"><Input type="number" min={1} max={120} value={f.default_timeout_s} disabled={!canEdit} onChange={(e) => setF({ ...f, default_timeout_s: Number(e.target.value) || 1 })} /></Field>
        </div>
        <Field label="Base URL" hint="Test paths are appended to this. Private and internal addresses are blocked by the SSRF guard."><Input className="mono" value={f.base_url} disabled={!canEdit} onChange={(e) => setF({ ...f, base_url: e.target.value })} placeholder="https://api.example.com" /></Field>
        <Field label="Description"><Input value={f.description} disabled={!canEdit} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Variables" hint={<>Use as <span className="mono">{"{{name}}"}</span> in URLs, headers, bodies and auth. Stored encrypted, but visible to project members — don't put production secrets here.</>}>
          <KeyValueEditor value={vars} onChange={setVars} keyPlaceholder="variable" disabled={!canEdit} />
        </Field>
        {canEdit && <div><Button variant="primary" loading={update.isPending} onClick={save}>Save changes</Button></div>}
      </div>
    </Card>
  );
}

function Members() {
  const { projectId, isOwner } = useProjectCtx();
  const { user } = useAuth();
  const toast = useToast();
  const { data } = useMembers(projectId);
  const { add, update, remove } = useMemberMutations(projectId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"editor" | "viewer">("editor");
  const [err, setErr] = useState<string | null>(null);
  const invite = () => {
    setErr(null);
    add.mutate({ email: email.trim(), role }, { onSuccess: () => { setEmail(""); toast.success("Member added"); }, onError: (e) => setErr(errorMessage(e)) });
  };
  return (
    <Card>
      <CardHeader title="Members" />
      <div className="card-body stack">
        <p className="dim" style={{ fontSize: 13 }}><b>Owner</b> manages everything · <b>Editor</b> edits tests and starts runs · <b>Viewer</b> is read-only. People must already have a TestPilot account.</p>
        {isOwner && (<>
          <div className="row wrap"><Input style={{ flex: 1, minWidth: 200 }} type="email" placeholder="teammate@company.com" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && email && invite()} />
            <Select style={{ width: 120 }} value={role} onChange={(e) => setRole(e.target.value as "editor" | "viewer")}><option value="editor">Editor</option><option value="viewer">Viewer</option></Select>
            <Button icon={UserPlus} loading={add.isPending} disabled={!email.trim()} onClick={invite}>Add</Button></div>
          {err && <Alert tone="danger">{err}</Alert>}
        </>)}
        <div className="table-wrap"><table className="table"><tbody>
          {data?.map((m) => (
            <tr key={m.user_id}>
              <td><b>{m.full_name}</b>{m.user_id === user?.id && <span className="faint"> (you)</span>}<div className="faint" style={{ fontSize: 12 }}>{m.email}</div></td>
              <td style={{ width: 150 }}>{isOwner && m.role !== "owner"
                ? <Select value={m.role} onChange={(e) => update.mutate({ userId: m.user_id, role: e.target.value as "editor" | "viewer" }, { onError: (er) => toast.error("Could not change role", errorMessage(er)) })}><option value="editor">Editor</option><option value="viewer">Viewer</option></Select>
                : <Badge tone={m.role === "owner" ? "accent" : undefined}>{m.role}</Badge>}</td>
              <td className="right" style={{ width: 50 }}>{isOwner && m.role !== "owner" && <Button size="sm" variant="ghost" iconOnly icon={Trash2} aria-label="Remove member" onClick={() => remove.mutate(m.user_id, { onSuccess: () => toast.success("Member removed") })} />}</td>
            </tr>))}
        </tbody></table></div>
      </div>
    </Card>
  );
}

function ApiKeys() {
  const { projectId, canEdit } = useProjectCtx();
  const toast = useToast();
  const { data } = useApiKeys(projectId, canEdit);
  const { create, revoke } = useApiKeyMutations(projectId);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [revoking, setRevoking] = useState<number | null>(null);
  if (!canEdit) return null;
  const snippet = `# .github/workflows/api-regression.yml (step)
- name: Run TestPilot suite
  env:
    TESTPILOT_URL: \${{ vars.TESTPILOT_URL }}
    TESTPILOT_API_KEY: \${{ secrets.TESTPILOT_API_KEY }}
  run: |
    curl -fsS -X POST "$TESTPILOT_URL/api/v1/ci/runs" \\
      -H "X-API-Key: $TESTPILOT_API_KEY" -H "Content-Type: application/json" \\
      -d '{"label":"'"$GITHUB_SHA"'"}'
    # then poll GET /api/v1/ci/runs/{id}?fail_on_performance=false
    # until "conclusion" is success or failure (see scripts/testpilot-ci.sh)`;
  return (
    <Card>
      <CardHeader title="CI API keys" />
      <div className="card-body stack">
        <p className="dim" style={{ fontSize: 13 }}>Keys let CI pipelines start runs and read their conclusion. Only a hash is stored, so a key is shown once.</p>
        <div className="row"><Input style={{ flex: 1 }} placeholder="Key name, e.g. GitHub Actions" value={name} onChange={(e) => setName(e.target.value)} />
          <Button icon={Plus} loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate(name.trim(), { onSuccess: (k) => { setCreated(k); setName(""); }, onError: (e) => toast.error("Could not create key", errorMessage(e)) })}>Create key</Button></div>
        {!data?.length ? <EmptyState icon={KeyRound} title="No API keys">Create one to trigger runs from CI.</EmptyState> : (
          <div className="table-wrap"><table className="table"><tbody>
            {data.map((k) => (
              <tr key={k.id}><td><b>{k.name}</b><div className="mono faint" style={{ fontSize: 12 }}>{k.prefix}…</div></td>
                <td className="dim">{k.revoked ? <Badge tone="danger">Revoked</Badge> : k.last_used_at ? `Used ${timeAgo(k.last_used_at)}` : "Never used"}</td>
                <td className="right">{!k.revoked && <Button size="sm" variant="ghost" onClick={() => setRevoking(k.id)}>Revoke</Button>}</td></tr>))}
          </tbody></table></div>
        )}
        <CodeBlock>{snippet}</CodeBlock>
      </div>
      {created && (
        <Modal title="Copy your API key" onClose={() => setCreated(null)} footer={<Button variant="primary" onClick={() => setCreated(null)}>I've saved it</Button>}>
          <div className="stack"><Alert tone="warning">This is the only time the full key is shown.</Alert><CodeBlock>{created.key}</CodeBlock></div>
        </Modal>
      )}
      {revoking !== null && <ConfirmDialog title="Revoke key" confirmLabel="Revoke" message="Pipelines using this key will stop working immediately." loading={revoke.isPending} onClose={() => setRevoking(null)}
        onConfirm={() => revoke.mutate(revoking, { onSuccess: () => { toast.success("Key revoked"); setRevoking(null); } })} />}
    </Card>
  );
}

function Danger() {
  const { project, projectId, isOwner } = useProjectCtx();
  const nav = useNavigate();
  const toast = useToast();
  const del = useDeleteProject();
  const [open, setOpen] = useState(false);
  if (!isOwner) return null;
  return (
    <Card>
      <CardHeader title="Danger zone" />
      <div className="card-body row between wrap">
        <span className="dim">Permanently delete <b>{project.name}</b> with all tests, runs and schedules.</span>
        <Button variant="danger" icon={Trash2} onClick={() => setOpen(true)}>Delete project</Button>
      </div>
      {open && <ConfirmDialog title="Delete project" message={<>This permanently deletes <b>{project.name}</b> and everything in it. This cannot be undone.</>} loading={del.isPending} onClose={() => setOpen(false)}
        onConfirm={() => del.mutate(projectId, { onSuccess: () => { toast.success("Project deleted"); nav("/projects"); } })} />}
    </Card>
  );
}

export default function SettingsPage() {
  return <div className="stack" style={{ maxWidth: 860 }}><General /><Members /><ApiKeys /><Danger /></div>;
}

import { FlaskConical, FolderTree, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useCollectionMutations, useCollections } from "@/api/hooks";
import type { Collection } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { StartRunModal } from "@/components/StartRunModal";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Alert, Button, Card, EmptyState, Field, Input, PageSkeleton, Textarea } from "@/components/ui/ui";
import { plural } from "@/lib/format";

function CollectionModal({ existing, onClose }: { existing?: Collection; onClose: () => void }) {
  const { projectId } = useProjectCtx();
  const toast = useToast();
  const { create, update } = useCollectionMutations(projectId);
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const mutation = existing ? update : create;
  const submit = () => {
    const done = { onSuccess: () => { toast.success(existing ? "Collection updated" : "Collection created"); onClose(); } };
    if (existing) update.mutate({ id: existing.id, body: { name, description } }, done); else create.mutate({ name, description }, done);
  };
  return (
    <Modal title={existing ? "Edit collection" : "New collection"} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={mutation.isPending} disabled={!name.trim()} onClick={submit}>{existing ? "Save" : "Create"}</Button></>}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {mutation.error instanceof ApiError && <Alert tone="danger">{mutation.error.message}</Alert>}
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Smoke tests" autoFocus /></Field>
        <Field label="Description"><Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="When should this group run?" /></Field>
      </form>
    </Modal>
  );
}

export default function CollectionsPage() {
  const { projectId, canEdit } = useProjectCtx();
  const toast = useToast();
  const { data, isLoading } = useCollections(projectId);
  const { remove } = useCollectionMutations(projectId);
  const [editing, setEditing] = useState<Collection | "new" | null>(null);
  const [deleting, setDeleting] = useState<Collection | null>(null);
  const [running, setRunning] = useState<Collection | null>(null);

  if (isLoading) return <PageSkeleton />;
  return (
    <div className="stack">
      <div className="row between"><p className="dim">Collections group related tests so you can run or schedule them together (e.g. “Smoke”, “Checkout flow”).</p>
        {canEdit && <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>New collection</Button>}</div>
      {!data?.length ? <Card><EmptyState icon={FolderTree} title="No collections yet" action={canEdit ? <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>New collection</Button> : undefined}>Create a collection, then assign test cases to it from the test editor.</EmptyState></Card> : (
        <div className="grid-auto">
          {data.map((c) => (
            <Card key={c.id} className="project-card">
              <div className="row"><div className="avatar" style={{ borderRadius: 10 }}><FolderTree size={16} /></div><h3 className="truncate grow">{c.name}</h3></div>
              <p className="dim" style={{ minHeight: 40 }}>{c.description || "No description"}</p>
              <div className="meta"><span><FlaskConical size={14} />{plural(c.test_case_count, "test")}</span></div>
              <div className="row" style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                <Link className="btn sm" to={`/projects/${projectId}/tests?collection=${c.id}`}>View tests</Link>
                {canEdit && <Button size="sm" icon={Play} disabled={!c.test_case_count} onClick={() => setRunning(c)}>Run</Button>}
                <div className="spacer" />
                {canEdit && <><Button size="sm" variant="ghost" iconOnly icon={Pencil} aria-label={`Edit ${c.name}`} onClick={() => setEditing(c)} /><Button size="sm" variant="ghost" iconOnly icon={Trash2} aria-label={`Delete ${c.name}`} onClick={() => setDeleting(c)} /></>}
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && <CollectionModal existing={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      {running && <StartRunModal collectionId={running.id} onClose={() => setRunning(null)} />}
      {deleting && <ConfirmDialog title="Delete collection" message={<>Delete <b>{deleting.name}</b>? Its {plural(deleting.test_case_count, "test case")} will be kept but become uncategorised.</>} loading={remove.isPending}
        onClose={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting.id, { onSuccess: () => { toast.success("Collection deleted"); setDeleting(null); } })} />}
    </div>
  );
}

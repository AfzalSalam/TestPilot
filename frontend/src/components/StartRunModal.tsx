import { Play } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCollections, useRunMutations } from "@/api/hooks";
import { useProjectCtx } from "./layout/ProjectLayout";
import { Modal, useToast } from "./ui/overlays";
import { Alert, Button, Field, Input, Select } from "./ui/ui";

/** Starts a run for the whole project, a collection, or an explicit set of test cases. */
export function StartRunModal({ onClose, collectionId, testCaseIds }: { onClose: () => void; collectionId?: number | null; testCaseIds?: number[] }) {
  const { projectId } = useProjectCtx();
  const nav = useNavigate();
  const toast = useToast();
  const { data: collections } = useCollections(projectId);
  const { start } = useRunMutations(projectId);
  const [collection, setCollection] = useState<string>(collectionId ? String(collectionId) : "");
  const [concurrency, setConcurrency] = useState(5);
  const [label, setLabel] = useState("");
  const fixedSelection = !!testCaseIds?.length;

  const submit = () =>
    start.mutate(
      { collection_id: collection ? Number(collection) : null, test_case_ids: fixedSelection ? testCaseIds : undefined, concurrency, label },
      { onSuccess: (run) => { toast.success(`Run #${run.id} started`); onClose(); nav(`/projects/${projectId}/runs/${run.id}`); } },
    );

  return (
    <Modal title="Start a test run" onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" icon={Play} loading={start.isPending} onClick={submit}>Start run</Button></>}>
      <div className="stack">
        {start.error && <Alert tone="danger">{(start.error as Error).message}</Alert>}
        {fixedSelection
          ? <Alert tone="info">Running {testCaseIds!.length} selected test case{testCaseIds!.length === 1 ? "" : "s"}.</Alert>
          : (
            <Field label="What to run" hint="Only enabled test cases are executed">
              <Select value={collection} onChange={(e) => setCollection(e.target.value)}>
                <option value="">All enabled tests in this project</option>
                {collections?.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.test_case_count})</option>)}
              </Select>
            </Field>
          )}
        <Field label={`Concurrency: ${concurrency} parallel request${concurrency === 1 ? "" : "s"}`} hint="How many tests this run executes at the same time (server cap applies)">
          <input type="range" min={1} max={20} value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} aria-label="Concurrency" />
        </Field>
        <Field label="Label (optional)" hint="e.g. a commit SHA or release name; shown in run history">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="v2.4.1-rc1" maxLength={200} />
        </Field>
      </div>
    </Modal>
  );
}

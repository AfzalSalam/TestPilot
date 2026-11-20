// React Query hooks: one per backend capability. Mutations invalidate the queries they affect,
// so lists, counters and dashboards update without manual refetching.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "./client";
import type * as T from "./types";

const P = (id: number) => `/projects/${id}`;

export const qk = {
  health: ["health"] as const,
  dashboard: ["dashboard"] as const,
  projects: ["projects"] as const,
  project: (id: number) => ["project", id] as const,
  members: (id: number) => ["project", id, "members"] as const,
  endpoints: (id: number) => ["project", id, "endpoints"] as const,
  collections: (id: number) => ["project", id, "collections"] as const,
  testCases: (id: number) => ["project", id, "test-cases"] as const,
  runs: (id: number) => ["project", id, "runs"] as const,
  run: (id: number, runId: number) => ["project", id, "run", runId] as const,
  schedules: (id: number) => ["project", id, "schedules"] as const,
  keys: (id: number) => ["project", id, "api-keys"] as const,
  analytics: (id: number) => ["project", id, "analytics"] as const,
};

const ACTIVE: T.RunStatus[] = ["queued", "running"];
export const isActive = (s?: T.RunStatus) => !!s && ACTIVE.includes(s);

// ---------------------------------------------------------------- platform
export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: () => http.get<T.Health>("/health"), refetchInterval: 30_000, retry: false });

export const useDashboard = () =>
  useQuery({
    queryKey: qk.dashboard,
    queryFn: () => http.get<T.Dashboard>("/dashboard"),
    refetchInterval: (q) => (q.state.data?.active_runs ? 2000 : 20_000),
  });

// ---------------------------------------------------------------- projects & members
export const useProjects = () => useQuery({ queryKey: qk.projects, queryFn: () => http.get<T.Project[]>("/projects") });
export const useProject = (id: number) => useQuery({ queryKey: qk.project(id), queryFn: () => http.get<T.Project>(P(id)), enabled: id > 0 });

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: T.ProjectInput) => http.post<T.Project>("/projects", b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.projects }); qc.invalidateQueries({ queryKey: qk.dashboard }); },
  });
}
export function useUpdateProject(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: Partial<T.ProjectInput>) => http.patch<T.Project>(P(id), b),
    onSuccess: (data) => { qc.setQueryData(qk.project(id), data); qc.invalidateQueries({ queryKey: qk.projects }); },
  });
}
export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => http.del(P(id)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.projects }); qc.invalidateQueries({ queryKey: qk.dashboard }); },
  });
}

export const useMembers = (id: number) => useQuery({ queryKey: qk.members(id), queryFn: () => http.get<T.Member[]>(`${P(id)}/members`) });
export function useMemberMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: qk.members(id) });
  return {
    add: useMutation({ mutationFn: (b: { email: string; role: "editor" | "viewer" }) => http.post<T.Member>(`${P(id)}/members`, b), onSuccess: refresh }),
    update: useMutation({ mutationFn: (v: { userId: number; role: "editor" | "viewer" }) => http.patch<T.Member>(`${P(id)}/members/${v.userId}`, { role: v.role }), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (userId: number) => http.del(`${P(id)}/members/${userId}`), onSuccess: refresh }),
  };
}

// ---------------------------------------------------------------- endpoints
export const useEndpoints = (id: number) => useQuery({ queryKey: qk.endpoints(id), queryFn: () => http.get<T.Endpoint[]>(`${P(id)}/endpoints`) });
export function useEndpointMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: qk.endpoints(id) }); qc.invalidateQueries({ queryKey: qk.project(id) }); };
  return {
    create: useMutation({ mutationFn: (b: T.EndpointInput) => http.post<T.Endpoint>(`${P(id)}/endpoints`, b), onSuccess: refresh }),
    update: useMutation({ mutationFn: (v: { id: number; body: Partial<T.EndpointInput> }) => http.patch<T.Endpoint>(`${P(id)}/endpoints/${v.id}`, v.body), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (eid: number) => http.del(`${P(id)}/endpoints/${eid}`), onSuccess: refresh }),
  };
}

// ---------------------------------------------------------------- collections
export const useCollections = (id: number) => useQuery({ queryKey: qk.collections(id), queryFn: () => http.get<T.Collection[]>(`${P(id)}/collections`) });
export function useCollectionMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: qk.collections(id) });
    qc.invalidateQueries({ queryKey: qk.testCases(id) });
    qc.invalidateQueries({ queryKey: qk.project(id) });
  };
  return {
    create: useMutation({ mutationFn: (b: { name: string; description?: string }) => http.post<T.Collection>(`${P(id)}/collections`, b), onSuccess: refresh }),
    update: useMutation({ mutationFn: (v: { id: number; body: { name?: string; description?: string } }) => http.patch<T.Collection>(`${P(id)}/collections/${v.id}`, v.body), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (cid: number) => http.del(`${P(id)}/collections/${cid}`), onSuccess: refresh }),
  };
}

// ---------------------------------------------------------------- test cases
export const useTestCases = (id: number, filter: { collection_id?: number | null; q?: string; enabled?: boolean } = {}) =>
  useQuery({
    queryKey: [...qk.testCases(id), filter],
    queryFn: () => http.get<T.TestCase[]>(`${P(id)}/test-cases`, filter),
    placeholderData: keepPreviousData,
  });

export function useTestCaseMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: qk.testCases(id) });
    qc.invalidateQueries({ queryKey: qk.collections(id) });
    qc.invalidateQueries({ queryKey: qk.project(id) });
  };
  return {
    create: useMutation({ mutationFn: (b: T.TestCaseInput) => http.post<T.TestCase>(`${P(id)}/test-cases`, b), onSuccess: refresh }),
    update: useMutation({ mutationFn: (v: { id: number; body: Partial<T.TestCaseInput> }) => http.patch<T.TestCase>(`${P(id)}/test-cases/${v.id}`, v.body), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (tid: number) => http.del(`${P(id)}/test-cases/${tid}`), onSuccess: refresh }),
    duplicate: useMutation({ mutationFn: (tid: number) => http.post<T.TestCase>(`${P(id)}/test-cases/${tid}/duplicate`), onSuccess: refresh }),
    // "Send" button: executes without storing a result
    tryUnsaved: useMutation({ mutationFn: (b: T.TestCaseInput) => http.post<T.ExecuteResult>(`${P(id)}/test-cases/execute`, b) }),
    trySaved: useMutation({ mutationFn: (tid: number) => http.post<T.ExecuteResult>(`${P(id)}/test-cases/${tid}/execute`) }),
  };
}

// ---------------------------------------------------------------- runs
export const useRuns = (id: number, params: { status?: string; trigger?: string; collection_id?: number | null; limit?: number; offset?: number } = {}) =>
  useQuery({
    queryKey: [...qk.runs(id), params],
    queryFn: () => http.get<T.Page<T.Run>>(`${P(id)}/runs`, params),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((r) => isActive(r.status)) ? 1500 : false),
  });

export const useRun = (id: number, runId: number) =>
  useQuery({
    queryKey: qk.run(id, runId),
    queryFn: () => http.get<T.Run>(`${P(id)}/runs/${runId}`),
    refetchInterval: (q) => (isActive(q.state.data?.status) ? 1000 : false),
  });

export const useResults = (id: number, runId: number, status?: string, live = false) =>
  useQuery({
    queryKey: [...qk.run(id, runId), "results", status ?? "all"],
    queryFn: () => http.get<T.Page<T.Result>>(`${P(id)}/runs/${runId}/results`, { status, limit: 500 }),
    refetchInterval: live ? 1000 : false,
  });

export const useRegression = (id: number, runId: number, baselineRunId?: number | null, enabled = true) =>
  useQuery({
    queryKey: [...qk.run(id, runId), "regression", baselineRunId ?? "default"],
    queryFn: () => http.get<T.RegressionReport>(`${P(id)}/runs/${runId}/regression`, { baseline_run_id: baselineRunId ?? undefined }),
    enabled,
  });

export function useRunMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: qk.runs(id) });
    qc.invalidateQueries({ queryKey: qk.analytics(id) });
    qc.invalidateQueries({ queryKey: qk.project(id) });
    qc.invalidateQueries({ queryKey: qk.projects });
    qc.invalidateQueries({ queryKey: qk.dashboard });
  };
  return {
    start: useMutation({
      mutationFn: (b: { collection_id?: number | null; test_case_ids?: number[]; concurrency?: number; label?: string }) => http.post<T.Run>(`${P(id)}/runs`, b),
      onSuccess: refresh,
    }),
    cancel: useMutation({ mutationFn: (runId: number) => http.post<T.Run>(`${P(id)}/runs/${runId}/cancel`), onSuccess: refresh }),
    rerun: useMutation({ mutationFn: (runId: number) => http.post<T.Run>(`${P(id)}/runs/${runId}/rerun`), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (runId: number) => http.del(`${P(id)}/runs/${runId}`), onSuccess: refresh }),
  };
}

// ---------------------------------------------------------------- schedules
export const useSchedules = (id: number) => useQuery({ queryKey: qk.schedules(id), queryFn: () => http.get<T.Schedule[]>(`${P(id)}/schedules`), refetchInterval: 30_000 });
export const useCronPreview = (id: number, cron: string) =>
  useQuery({ queryKey: ["cron-preview", id, cron], queryFn: () => http.get<T.CronPreview>(`${P(id)}/schedules/preview`, { cron }), enabled: cron.trim().length >= 9, retry: false });

export function useScheduleMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: qk.schedules(id) }); qc.invalidateQueries({ queryKey: qk.analytics(id) }); };
  type Body = { name?: string; cron?: string; collection_id?: number | null; concurrency?: number; enabled?: boolean };
  return {
    create: useMutation({ mutationFn: (b: Body & { name: string; cron: string }) => http.post<T.Schedule>(`${P(id)}/schedules`, b), onSuccess: refresh }),
    update: useMutation({ mutationFn: (v: { id: number; body: Body }) => http.patch<T.Schedule>(`${P(id)}/schedules/${v.id}`, v.body), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (sid: number) => http.del(`${P(id)}/schedules/${sid}`), onSuccess: refresh }),
    trigger: useMutation({ mutationFn: (sid: number) => http.post<T.Run>(`${P(id)}/schedules/${sid}/trigger`), onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: qk.runs(id) }); } }),
  };
}

// ---------------------------------------------------------------- API keys, import, analytics
export const useApiKeys = (id: number, enabled = true) => useQuery({ queryKey: qk.keys(id), queryFn: () => http.get<T.ApiKey[]>(`${P(id)}/api-keys`), enabled });
export function useApiKeyMutations(id: number) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: qk.keys(id) });
  return {
    create: useMutation({ mutationFn: (name: string) => http.post<T.ApiKeyCreated>(`${P(id)}/api-keys`, { name }), onSuccess: refresh }),
    revoke: useMutation({ mutationFn: (kid: number) => http.del(`${P(id)}/api-keys/${kid}`), onSuccess: refresh }),
  };
}

export function useImportOpenApi(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { spec_text: string; create_test_cases: boolean; create_collection: boolean; set_base_url: boolean }) => http.post<T.ImportResult>(`${P(id)}/import/openapi`, b),
    onSuccess: () => { for (const k of [qk.endpoints(id), qk.testCases(id), qk.collections(id), qk.project(id)]) qc.invalidateQueries({ queryKey: k }); },
  });
}

export const useAnalytics = (id: number) =>
  useQuery({ queryKey: qk.analytics(id), queryFn: () => http.get<T.Analytics>(`${P(id)}/analytics`), refetchInterval: 15_000 });

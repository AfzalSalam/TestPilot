import { Activity, CalendarClock, FileUp, FlaskConical, FolderTree, Gauge, Globe, History, Settings } from "lucide-react";
import { createContext, useContext } from "react";
import { Outlet, useParams } from "react-router-dom";
import { useProject } from "@/api/hooks";
import type { Project, Role } from "@/api/types";
import { ApiError } from "@/api/client";
import { Badge, EmptyState, PageSkeleton, Tabs } from "../ui/ui";
import { Link } from "react-router-dom";

interface Ctx { project: Project; projectId: number; role: Role; canEdit: boolean; isOwner: boolean }
const ProjectCtx = createContext<Ctx | null>(null);

export function useProjectCtx(): Ctx {
  const ctx = useContext(ProjectCtx);
  if (!ctx) throw new Error("useProjectCtx must be used inside <ProjectLayout>");
  return ctx;
}

export function ProjectLayout() {
  const { projectId: raw } = useParams();
  const projectId = Number(raw);
  const { data: project, error, isLoading } = useProject(projectId);

  if (isLoading) return <div className="page"><PageSkeleton /></div>;
  if (error || !project) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="page"><div className="card">
        <EmptyState icon={Globe} title={notFound ? "Project not found" : "Could not load project"} action={<Link className="btn" to="/projects">Back to projects</Link>}>
          {notFound ? "It may have been deleted, or you don't have access to it." : (error as Error)?.message}
        </EmptyState>
      </div></div>
    );
  }

  const base = `/projects/${projectId}`;
  return (
    <ProjectCtx.Provider value={{ project, projectId, role: project.role, canEdit: project.role !== "viewer", isOwner: project.role === "owner" }}>
      <div className="page">
        <div className="page-header" style={{ marginBottom: 14 }}>
          <div className="grow">
            <div className="row wrap"><h1>{project.name}</h1><Badge tone={project.role === "owner" ? "accent" : undefined}>{project.role}</Badge></div>
            <p className="sub">{project.description || "No description"}{project.base_url && <> · <span className="mono">{project.base_url}</span></>}</p>
          </div>
        </div>
        <Tabs items={[
          { to: base, label: "Overview", icon: Gauge, end: true },
          { to: `${base}/tests`, label: "Test cases", icon: FlaskConical, count: project.test_case_count },
          { to: `${base}/collections`, label: "Collections", icon: FolderTree, count: project.collection_count },
          { to: `${base}/endpoints`, label: "Endpoints", icon: Activity, count: project.endpoint_count },
          { to: `${base}/runs`, label: "Runs", icon: History, count: project.run_count },
          { to: `${base}/schedules`, label: "Schedules", icon: CalendarClock },
          { to: `${base}/import`, label: "Import", icon: FileUp },
          { to: `${base}/settings`, label: "Settings", icon: Settings },
        ]} />
        <div style={{ paddingTop: 24 }}><Outlet /></div>
      </div>
    </ProjectCtx.Provider>
  );
}

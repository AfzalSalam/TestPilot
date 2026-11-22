import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/layout/AppShell";
import { ProjectLayout } from "./components/layout/ProjectLayout";
import { PageSkeleton } from "./components/ui/ui";

// Lazy-loaded pages — each becomes its own JS chunk
const LoginPage = lazy(() => import("./pages/Login"));
const DashboardPage = lazy(() => import("./pages/Dashboard"));
const ProjectsPage = lazy(() => import("./pages/Projects"));
const ProjectOverview = lazy(() => import("./pages/ProjectOverview"));
const TestCasesPage = lazy(() => import("./pages/TestCases"));
const EndpointsPage = lazy(() => import("./pages/Endpoints"));
const CollectionsPage = lazy(() => import("./pages/Collections"));
const RunsPage = lazy(() => import("./pages/Runs"));
const RunDetailPage = lazy(() => import("./pages/RunDetail"));
const SchedulesPage = lazy(() => import("./pages/Schedules"));
const ImportPage = lazy(() => import("./pages/ImportPage"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const NotFound = lazy(() => import("./pages/NotFound"));

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div style={{ padding: 40 }}><PageSkeleton /></div>;
  return user ? children : <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

const Loader = () => <div style={{ padding: 40 }}><PageSkeleton /></div>;

export default function App() {
  return (
    <Suspense fallback={<Loader />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth><AppShell /></RequireAuth>}>
          <Route index element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectLayout />}>
            <Route index element={<ProjectOverview />} />
            <Route path="tests" element={<TestCasesPage />} />
            <Route path="endpoints" element={<EndpointsPage />} />
            <Route path="collections" element={<CollectionsPage />} />
            <Route path="runs" element={<RunsPage />} />
            <Route path="runs/:runId" element={<RunDetailPage />} />
            <Route path="schedules" element={<SchedulesPage />} />
            <Route path="import" element={<ImportPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

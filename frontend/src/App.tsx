import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/layout/AppShell";
import { ProjectLayout } from "./components/layout/ProjectLayout";
import { PageSkeleton } from "./components/ui/ui";
import CollectionsPage from "./pages/Collections";
import DashboardPage from "./pages/Dashboard";
import EndpointsPage from "./pages/Endpoints";
import ImportPage from "./pages/ImportPage";
import LoginPage from "./pages/Login";
import NotFound from "./pages/NotFound";
import ProjectOverview from "./pages/ProjectOverview";
import ProjectsPage from "./pages/Projects";
import RunDetailPage from "./pages/RunDetail";
import RunsPage from "./pages/Runs";
import SchedulesPage from "./pages/Schedules";
import SettingsPage from "./pages/Settings";
import TestCasesPage from "./pages/TestCases";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div style={{ padding: 40 }}><PageSkeleton /></div>;
  return user ? children : <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

export default function App() {
  return (
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
  );
}

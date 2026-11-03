import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "./shell/AppShell";
import { ProjectLayout } from "./shell/ProjectLayout";
import { HomePage } from "./pages/HomePage";
import { OverviewPage } from "./pages/OverviewPage";
import { IntakePage } from "./pages/IntakePage";
import { ArtifactsPage } from "./pages/ArtifactsPage";
import { TestsPage } from "./pages/TestsPage";
import { ResearchPage } from "./pages/ResearchPage";
import { ConductorPage } from "./pages/ConductorPage";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { FindingsPage } from "./pages/FindingsPage";
import { FindingDetailPage } from "./pages/FindingDetailPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ChangesPage } from "./pages/ChangesPage";
import { ReportsPage } from "./pages/ReportsPage";
import { ProjectSettingsPage } from "./pages/ProjectSettingsPage";
import { MemoryPage } from "./pages/MemoryPage";
import { SampleDataSettingsPage } from "./pages/SampleDataSettingsPage";
import { NotFoundPage } from "./pages/NotFoundPage";

const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/settings/sample-data", element: <SampleDataSettingsPage /> },
      {
        path: "/p/:id",
        element: <ProjectLayout />,
        children: [
          { index: true, element: <OverviewPage /> },
          { path: "intake", element: <IntakePage /> },
          { path: "artifacts", element: <ArtifactsPage /> },
          { path: "tests", element: <TestsPage /> },
          { path: "research", element: <ResearchPage /> },
          { path: "conductor", element: <ConductorPage /> },
          { path: "runs", element: <RunsPage /> },
          { path: "runs/:runId", element: <RunDetailPage /> },
          { path: "findings", element: <FindingsPage /> },
          { path: "findings/:fid", element: <FindingDetailPage /> },
          { path: "approvals", element: <ApprovalsPage /> },
          { path: "changes", element: <ChangesPage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "settings", element: <ProjectSettingsPage /> },
          { path: "memory", element: <MemoryPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
], { basename });

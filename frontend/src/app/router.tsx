import { createBrowserRouter, Navigate } from "react-router";

import { Layout } from "../components/Layout";
import { ApplicationWorkspacePage } from "../pages/ApplicationWorkspacePage";
import { ApplicationsPage } from "../pages/ApplicationsPage";
import { DiscoveryPage } from "../pages/DiscoveryPage";
import { MasterCvPage } from "../pages/MasterCvPage";
import { MatchesPage } from "../pages/MatchesPage";
import { OverviewPage } from "../pages/OverviewPage";
import { SettingsPage } from "../pages/SettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "master-cv", element: <MasterCvPage /> },
      { path: "discovery", element: <DiscoveryPage /> },
      { path: "matches", element: <MatchesPage /> },
      { path: "applications", element: <ApplicationsPage /> },
      { path: "applications/:id", element: <ApplicationWorkspacePage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

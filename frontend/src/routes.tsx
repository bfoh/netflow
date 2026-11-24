import type { RouteObject } from 'react-router';

import { AppLayout } from './components/AppLayout';
import { RouteError } from './components/RouteError';
import { AuditPage } from './pages/AuditPage';
import { ConfigurationsPage } from './pages/ConfigurationsPage';
import { DashboardPage } from './pages/DashboardPage';
import { DeploymentDetailPage } from './pages/DeploymentDetailPage';
import { DeploymentsPage } from './pages/DeploymentsPage';
import { DeviceDetailPage } from './pages/DeviceDetailPage';
import { DevicesPage } from './pages/DevicesPage';
import { FirmwarePage } from './pages/FirmwarePage';
import { ProvisioningPage } from './pages/ProvisioningPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { SettingsPage } from './pages/SettingsPage';
import { StagingPage } from './pages/StagingPage';
import { TopologyPage } from './pages/TopologyPage';

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppLayout />,
    errorElement: <RouteError />,
    children: [
      {
        // Pathless layout route: a crash in one page renders RouteError inside the app shell.
        errorElement: <RouteError />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: 'projects', element: <ProjectsPage /> },
          { path: 'projects/:projectId', element: <ProjectDetailPage /> },
          { path: 'devices', element: <DevicesPage /> },
          { path: 'devices/:deviceId', element: <DeviceDetailPage /> },
          { path: 'topology', element: <TopologyPage /> },
          { path: 'configurations', element: <ConfigurationsPage /> },
          { path: 'provisioning', element: <ProvisioningPage /> },
          { path: 'firmware', element: <FirmwarePage /> },
          { path: 'deployments', element: <DeploymentsPage /> },
          { path: 'deployments/:deploymentId', element: <DeploymentDetailPage /> },
          { path: 'staging/:stagingId', element: <StagingPage /> },
          { path: 'audit', element: <AuditPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
];


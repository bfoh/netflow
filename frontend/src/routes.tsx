import type { RouteObject } from 'react-router';

import { AppLayout } from './components/AppLayout';
import { AuditPage } from './pages/AuditPage';
import { ConfigurationsPage } from './pages/ConfigurationsPage';
import { DashboardPage } from './pages/DashboardPage';
import { DeploymentDetailPage } from './pages/DeploymentDetailPage';
import { DeploymentsPage } from './pages/DeploymentsPage';
import { DeviceDetailPage } from './pages/DeviceDetailPage';
import { DevicesPage } from './pages/DevicesPage';
import { FirmwarePage, ProvisioningPage, TopologyPage } from './pages/PlannedPages';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { SettingsPage } from './pages/SettingsPage';

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppLayout />,
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
      { path: 'audit', element: <AuditPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];


import type { RouteObject } from 'react-router';

import { AppLayout } from './components/AppLayout';
import { Moved } from './components/Moved';
import { RouteError } from './components/RouteError';
import { AuditPage } from './pages/AuditPage';
import { DashboardPage } from './pages/DashboardPage';
import { DeploymentDetailPage } from './pages/DeploymentDetailPage';
import { DeploymentsPage } from './pages/DeploymentsPage';
import { DeviceDetailPage } from './pages/DeviceDetailPage';
import { DevicesPage } from './pages/DevicesPage';
import { FirmwarePage } from './pages/FirmwarePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ProvisioningPage } from './pages/ProvisioningPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { SettingsPage } from './pages/SettingsPage';
import { StageSystemPage } from './pages/StageSystemPage';
import { StagingPage } from './pages/StagingPage';
import { TopologyPage } from './pages/TopologyPage';
import { paths } from './paths';

const withQuery = (path: string, query: URLSearchParams) => (query.toString() ? `${path}?${query}` : path);

/** The old Files page: one device's files are now its device page's Files tab. */
function filesOf(query: URLSearchParams) {
  const device = query.get('device');
  return device ? paths.device(device, 'files', query.get('version') ?? undefined) : paths.devices;
}

/** The old plan form took `project`; the new one takes `system`. */
function newPlanFrom(query: URLSearchParams) {
  const project = query.get('project');
  if (project) { query.delete('project'); query.set('system', project); }
  return withQuery(query.get('system') || query.get('devices') ? '/plans/new' : paths.plans, query);
}

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
          { path: 'stage', element: <StageSystemPage /> },
          { path: 'stage/:projectId', element: <StageSystemPage /> },
          { path: 'systems', element: <ProjectsPage /> },
          { path: 'systems/:projectId', element: <ProjectDetailPage /> },
          { path: 'devices', element: <DevicesPage /> },
          { path: 'devices/:deviceId', element: <DeviceDetailPage /> },
          { path: 'plans', element: <DeploymentsPage /> },
          { path: 'plans/new', element: <DeploymentsPage /> },
          { path: 'plans/staging/:stagingId', element: <StagingPage /> },
          { path: 'plans/:deploymentId', element: <DeploymentDetailPage /> },
          { path: 'console', element: <ProvisioningPage /> },
          { path: 'firmware', element: <FirmwarePage /> },
          { path: 'topology', element: <TopologyPage /> },
          { path: 'audit', element: <AuditPage /> },
          { path: 'settings', element: <SettingsPage /> },
          // Addresses before D-120.
          { path: 'projects', element: <Moved to={(_, q) => withQuery(paths.systems, q)} /> },
          { path: 'projects/:projectId', element: <Moved to={(p, q) => withQuery(`/systems/${p.projectId}`, q)} /> },
          { path: 'deployments', element: <Moved to={(_, q) => newPlanFrom(q)} /> },
          { path: 'deployments/:deploymentId', element: <Moved to={(p) => paths.plan(p.deploymentId ?? '')} /> },
          { path: 'staging/:stagingId', element: <Moved to={(p) => paths.staging(p.stagingId ?? '')} /> },
          { path: 'provisioning', element: <Moved to={(_, q) => withQuery('/console', q)} /> },
          { path: 'configurations', element: <Moved to={(_, q) => filesOf(q)} /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

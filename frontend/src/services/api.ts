import type {
  AuditEvent, ConfigDiff, ConfigVersion, Deployment, DeploymentSummary, Device, DeviceInput, DeviceIntent,
  DeviceModel, Driver, GenerateResult, OperationResult, Project,
} from '../types/api';

const ACTOR_KEY = 'undm.actor';

/** Name used to attribute actions. Attribution only: the API has no authentication yet. */
export function getActor(): string {
  try {
    return localStorage.getItem(ACTOR_KEY) || 'local-user';
  } catch {
    return 'local-user';
  }
}

export function setActor(name: string): void {
  try {
    localStorage.setItem(ACTOR_KEY, name);
  } catch {
    /* storage unavailable: fall back to default */
  }
}

export class ApiError extends Error {
  readonly status: number;
  readonly details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

function describe(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const b = body as { error?: string; detail?: unknown };
    if (b.error) return b.error;
    if (Array.isArray(b.detail)) {
      return b.detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          `${(d.loc ?? []).slice(1).join('.')}: ${d.msg ?? 'invalid'}`)
        .join('; ');
    }
    if (typeof b.detail === 'string') return b.detail;
  }
  return `Request failed (${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-UNDM-Actor': getActor() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const details = data && typeof data === 'object' ? (data as { details?: unknown }).details : undefined;
    throw new ApiError(res.status, describe(data, res.status), details);
  }
  return data as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>('GET', '/health'),
  drivers: () => request<Driver[]>('GET', '/drivers'),
  deviceModels: () => request<DeviceModel[]>('GET', '/device-models'),

  projects: () => request<Project[]>('GET', '/projects'),
  project: (id: string) => request<Project>('GET', `/projects/${id}`),
  createProject: (body: Partial<Project>) => request<Project>('POST', '/projects', body),
  updateProject: (id: string, body: Partial<Project>) =>
    request<Project>('PATCH', `/projects/${id}`, body),
  deleteProject: (id: string) => request<void>('DELETE', `/projects/${id}`),

  allDevices: () => request<Device[]>('GET', '/devices'),
  projectDevices: (pid: string) => request<Device[]>('GET', `/projects/${pid}/devices`),
  device: (id: string) => request<Device>('GET', `/devices/${id}`),
  createDevice: (pid: string, body: DeviceInput) =>
    request<Device>('POST', `/projects/${pid}/devices`, body),
  updateDevice: (id: string, body: DeviceInput) => request<Device>('PATCH', `/devices/${id}`, body),
  deleteDevice: (id: string) => request<void>('DELETE', `/devices/${id}`),
  setIntent: (id: string, intent: DeviceIntent) =>
    request<Device>('PUT', `/devices/${id}/intent`, intent),
  generateConfig: (id: string) => request<GenerateResult>('POST', `/devices/${id}/configs/generate`),
  configs: (id: string) => request<ConfigVersion[]>('GET', `/devices/${id}/configs`),
  config: (versionId: string) => request<ConfigVersion>('GET', `/configs/${versionId}`),
  configDiff: (fromVersion: string, toVersion: string) =>
    request<ConfigDiff>('GET', `/configs/diff?from_version=${fromVersion}&to_version=${toVersion}`),
  runOperation: (id: string, op: string) =>
    request<OperationResult>('POST', `/devices/${id}/operations/${op}`),

  allDeployments: (limit = 50) => request<DeploymentSummary[]>('GET', `/deployments?limit=${limit}`),
  deployments: (pid: string) => request<DeploymentSummary[]>('GET', `/projects/${pid}/deployments`),
  deployment: (id: string) => request<Deployment>('GET', `/deployments/${id}`),
  createDeployment: (pid: string, body: { device_ids: string[]; dry_run: boolean; apply_mode: string }) =>
    request<Deployment>('POST', `/projects/${pid}/deployments`, body),
  approveDeployment: (id: string) => request<Deployment>('POST', `/deployments/${id}/approve`),
  executeDeployment: (id: string) => request<Deployment>('POST', `/deployments/${id}/execute`),
  cancelDeployment: (id: string) => request<Deployment>('POST', `/deployments/${id}/cancel`),

  audit: (params: { limit?: number; target_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', String(params.limit));
    if (params.target_id) q.set('target_id', params.target_id);
    const qs = q.toString();
    return request<AuditEvent[]>('GET', `/audit${qs ? `?${qs}` : ''}`);
  },
};

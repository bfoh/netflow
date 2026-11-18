import type {
  AuditEvent, BootstrapPreview, BootstrapProfile, BootstrapResult, Compatibility, SerialPort, Topology, TopologyLink, TopologyLinkInput, ConfigDiff, ConfigVersion, CredentialRef, FirmwareImage, Policy, Deployment, DeploymentSummary, Device, DeviceInput, DeviceIntent,
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
  const isForm = body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    method,
    headers: isForm ? { 'X-UNDM-Actor': getActor() }
      : { 'Content-Type': 'application/json', 'X-UNDM-Actor': getActor() },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
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
  policy: () => request<Policy>('GET', '/policy'),
  credentialRefs: (pid: string) => request<CredentialRef[]>('GET', `/projects/${pid}/credential-refs`),
  createCredentialRef: (pid: string, body: { name: string; provider?: string; locator?: string }) =>
    request<CredentialRef>('POST', `/projects/${pid}/credential-refs`, body),
  setCredentialSecret: (refId: string, username: string, password: string) =>
    request<CredentialRef>('PUT', `/credential-refs/${refId}/secret`, { username, password }),
  deleteCredentialRef: (refId: string) => request<void>('DELETE', `/credential-refs/${refId}`),
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
  importConfig: (id: string, filename: string, text: string) =>
    request<ConfigVersion>('POST', `/devices/${id}/configs/import`, { filename, text }),
  configs: (id: string) => request<ConfigVersion[]>('GET', `/devices/${id}/configs`),
  config: (versionId: string) => request<ConfigVersion>('GET', `/configs/${versionId}`),
  configDiff: (fromVersion: string, toVersion: string) =>
    request<ConfigDiff>('GET', `/configs/diff?from_version=${fromVersion}&to_version=${toVersion}`),
  diagnostics: (id: string) => request<{ text: string }>('GET', `/devices/${id}/diagnostics`),
  runOperation: (id: string, op: string) =>
    request<OperationResult>('POST', `/devices/${id}/operations/${op}`),

  allDeployments: (limit = 50) => request<DeploymentSummary[]>('GET', `/deployments?limit=${limit}`),
  deployments: (pid: string) => request<DeploymentSummary[]>('GET', `/projects/${pid}/deployments`),
  deployment: (id: string) => request<Deployment>('GET', `/deployments/${id}`),
  createDeployment: (pid: string, body: {
    device_ids: string[]; dry_run: boolean; apply_mode: string; config_versions?: Record<string, string>;
  }) =>
    request<Deployment>('POST', `/projects/${pid}/deployments`, body),
  approveDeployment: (id: string, window?: { window_start: string; window_end: string }) =>
    request<Deployment>('POST', `/deployments/${id}/approve`, window),
  firmwareImages: () => request<FirmwareImage[]>('GET', '/firmware/images'),
  uploadFirmware: (form: FormData) => request<FirmwareImage>('POST', '/firmware/images', form),
  approveFirmware: (id: string) => request<FirmwareImage>('POST', `/firmware/images/${id}/approve`),
  retireFirmware: (id: string) => request<FirmwareImage>('POST', `/firmware/images/${id}/retire`),
  deleteFirmware: (id: string) => request<void>('DELETE', `/firmware/images/${id}`),
  firmwareCompatibility: (id: string, deviceIds: string[]) =>
    request<Compatibility[]>('POST', `/firmware/images/${id}/compatibility`, { device_ids: deviceIds }),
  createFirmwareDeployment: (pid: string, body: { device_ids: string[]; image_id: string; dry_run: boolean }) =>
    request<Deployment>('POST', `/projects/${pid}/firmware-upgrades`, body),
  executeDeployment: (id: string) => request<Deployment>('POST', `/deployments/${id}/execute`),
  cancelDeployment: (id: string) => request<Deployment>('POST', `/deployments/${id}/cancel`),

  serialPorts: () => request<SerialPort[]>('GET', '/provisioning/serial-ports'),
  bootstrapPreview: (id: string, profile: BootstrapProfile) =>
    request<BootstrapPreview>('POST', `/devices/${id}/provisioning/console-bootstrap/preview`, { profile }),
  consoleBootstrap: (id: string, body: {
    serial_port: string; baudrate: number; profile: BootstrapProfile; confirm_device_name: string; allow_configured: boolean;
  }) => request<BootstrapResult>('POST', `/devices/${id}/provisioning/console-bootstrap`, body),
  topology: (pid: string) => request<Topology>('GET', `/projects/${pid}/topology`),
  createLink: (pid: string, body: TopologyLinkInput) => request<TopologyLink>('POST', `/projects/${pid}/topology/links`, body),
  updateLink: (id: string, body: TopologyLinkInput) => request<TopologyLink>('PUT', `/topology/links/${id}`, body),
  deleteLink: (id: string) => request<void>('DELETE', `/topology/links/${id}`),
  savePositions: (pid: string, positions: Record<string, { x: number; y: number }>) =>
    request<Topology>('PUT', `/projects/${pid}/topology/positions`, positions),
  audit: (params: { limit?: number; target_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', String(params.limit));
    if (params.target_id) q.set('target_id', params.target_id);
    const qs = q.toString();
    return request<AuditEvent[]>('GET', `/audit${qs ? `?${qs}` : ''}`);
  },
};

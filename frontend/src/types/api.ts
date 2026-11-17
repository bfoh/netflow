// Mirrors backend/src/undm/api/schemas.py. Keep in sync when the API changes.

export type DeviceEnvironment = 'simulated' | 'lab' | 'production';
export type DeviceCategory =
  | 'switch' | 'router' | 'firewall' | 'server' | 'wireless_controller' | 'access_point' | 'other';

export interface Project {
  id: string;
  name: string;
  description: string;
  site: string;
  purpose: string;
  created_at: string;
  updated_at: string;
}

export interface VlanIntent { vlan_id: number; name?: string | null }
export interface InterfaceIntent {
  interface: string;
  address: string;
  description?: string | null;
  enabled?: boolean;
}
export interface StaticRouteIntent {
  prefix: string;
  next_hop: string;
  egress_interface?: string | null;
}
export interface DeviceIntent {
  hostname: string;
  vlans: VlanIntent[];
  interfaces: InterfaceIntent[];
  static_routes: StaticRouteIntent[];
}

export interface Device {
  id: string;
  project_id: string;
  name: string;
  manufacturer: string;
  product_family: string;
  model: string;
  hardware_revision: string;
  category: DeviceCategory;
  role: string;
  os_family: string;
  firmware_version: string;
  management_address: string;
  management_protocol: string;
  management_port: number | null;
  management_vrf: string;
  site: string;
  rack_location: string;
  driver_id: string;
  credential_ref_id: string | null;
  environment: DeviceEnvironment;
  provisioning_status: string;
  deployment_status: string;
  notes: string;
  tags: string[];
  intent: DeviceIntent | null;
  observed_facts: Record<string, unknown> | null;
  facts_retrieved_at: string | null;
  last_connection_at: string | null;
  last_backup_at: string | null;
  last_deployment_at: string | null;
  locked_by_deployment_id: string | null;
  capabilities: string[];
  created_at: string;
  updated_at: string;
}

export type DeviceInput = Partial<Omit<Device, 'id' | 'project_id' | 'created_at' | 'updated_at'>>;

export interface Driver {
  driver_id: string;
  vendor: string;
  platform: string;
  os_family: string;
  description: string;
  simulated: boolean;
  capabilities: string[];
}

export interface DeviceModel {
  model_id: string;
  manufacturer: string;
  product_family: string;
  model: string;
  category: DeviceCategory;
  os_family: string;
  drivers: string[];
  support: string;
  notes: string;
}

export interface Issue { severity: 'error' | 'warning'; code: string; message: string; path: string }

export interface ConfigVersion {
  id: string;
  device_id: string;
  kind: 'generated' | 'backup';
  sha256: string;
  platform: string;
  template_version: string;
  verification: string;
  reference: string;
  created_by: string;
  created_at: string;
  text?: string;
}

export interface GenerateResult { ok: boolean; issues: Issue[]; version: ConfigVersion | null }

export type DeploymentState =
  | 'draft' | 'validating' | 'awaiting_approval' | 'ready' | 'preflight' | 'backing_up'
  | 'deploying' | 'verifying' | 'recovering' | 'succeeded' | 'failed' | 'rolled_back'
  | 'recovery_required' | 'cancelled';

export interface DeploymentTarget {
  device_id: string;
  position: number;
  config_version_id: string;
  backup_version_id: string | null;
  state: string;
  diff: string;
  message: string;
}

export interface DeploymentEvent {
  seq: number;
  timestamp: string;
  device_id: string | null;
  stage: string;
  status: string;
  message: string;
}

export interface DeploymentSummary {
  id: string;
  project_id: string;
  state: DeploymentState;
  dry_run: boolean;
  apply_mode: string;
  created_by: string;
  approved_by: string | null;
  created_at: string;
}

export interface Deployment extends DeploymentSummary {
  approved_at: string | null;
  updated_at: string;
  targets: DeploymentTarget[];
  events: DeploymentEvent[];
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  outcome: string;
  details: Record<string, unknown>;
}

export interface OperationResult { status: string; message: string; data: unknown }

export interface ConfigDiff {
  from_version_id: string;
  to_version_id: string;
  unified: string;
  added: number;
  removed: number;
  changed: boolean;
}

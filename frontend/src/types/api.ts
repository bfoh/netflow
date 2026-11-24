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
  /** Answers to the switch's certificate questions (2930F); organisation details. */
  certificate_subject?: CertificateSubject | null;
  created_at: string;
  updated_at: string;
}

export interface CertificateSubject {
  common_name: string;
  org_unit: string;
  org_name: string;
  locality: string;
  state: string;
  country: string;
  profile_name: string;
  certificate_name: string;
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
  bootstrap_profile: BootstrapProfile | null;
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
  maturity: 'simulation' | 'experimental' | 'lab_validated';
  transport: string;
  notes: string[];
}

export interface CredentialRef {
  id: string;
  name: string;
  provider: 'keyring' | 'env';
  locator: string;
  has_secret: boolean | null;
}

export interface Policy {
  enable_real_device_writes: boolean;
  enable_real_device_firmware: boolean;
  allow_production_read_only: boolean;
  allow_production_deployments: boolean;
  require_separate_approver: boolean;
  firmware_require_separate_approver: boolean;
  /** Switches fixed by the start-up settings; they cannot be changed in Settings. */
  locked: string[];
}

export type SafetySwitch = 'enable_real_device_writes' | 'enable_real_device_firmware' | 'firmware_require_separate_approver';

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
  kind: 'generated' | 'backup' | 'imported';
  sha256: string;
  platform: string;
  template_version: string;
  verification: string;
  reference: string;
  created_by: string;
  created_at: string;
  text?: string;
  inspection?: ConfigInspection | null;
}

/** What an imported file is, worked out offline by the device's driver. Never contains secret values. */
export interface ConfigInspection {
  file_type: 'full_backup' | 'cli_script' | 'unknown';
  summary: string;
  apply_mode: 'merge' | 'replace' | null;
  facts: Record<string, string>;
  notes: string[];
  problems: string[];
  blocked_reason: string;
  secret_slots?: SecretSlot[];
}

/** A setting in a supplied file whose value can come from the credential store when sent. */
export interface SecretSlot { slot_id: string; setting: string; line: number }

export interface GenerateResult { ok: boolean; issues: Issue[]; version: ConfigVersion | null }

export type DeploymentState =
  | 'draft' | 'validating' | 'awaiting_approval' | 'ready' | 'preflight' | 'backing_up'
  | 'deploying' | 'verifying' | 'recovering' | 'succeeded' | 'failed' | 'rolled_back'
  | 'recovery_required' | 'cancelled';

export interface DeploymentTarget {
  device_id: string;
  position: number;
  config_version_id: string | null;
  /** Secret slot id -> credential reference id (never a value). */
  secret_refs?: Record<string, string> | null;
  /** Credential valid once the file is applied (the file changes the login). */
  credential_after_ref_id?: string | null;
  backup_version_id: string | null;
  /** Running configuration read back after the change (view it or compare it with what was sent). */
  after_version_id?: string | null;
  from_version: string | null;
  to_version: string | null;
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
  kind: 'configuration' | 'firmware' | 'first_login';
  state: DeploymentState;
  dry_run: boolean;
  /** Firmware plans: install the approved image even where a device runs a newer one. */
  allow_downgrade?: boolean;
  /** Firmware plans: also write the image into the secondary image slot. */
  also_secondary?: boolean;
  apply_mode: string;
  created_by: string;
  approved_by: string | null;
  created_at: string;
  /** Staging plans (D-071): steps share staging_id and run in staging_step order. */
  staging_id?: string | null;
  staging_step?: number | null;
}

/** One device: step 1 restores the base file (replace), step 2 loads the site file (merge). */
export interface StagingPlan {
  staging_id: string;
  steps: Deployment[];
}

/** One step of a device's staging plan, as sent to UNDM (D-085). */
export interface StagingStepInput {
  kind: 'first_login' | 'firmware' | 'configuration';
  image_id?: string;
  allow_downgrade?: boolean;
  also_secondary?: boolean;
  version_id?: string;
  credential_after_ref_id?: string;
  secrets?: Record<string, string>;
}

export interface StagingIndex {
  staging_id: string;
  device_id: string;
  created_at: string;
  kinds: string[];
  states: string[];
}

export interface Deployment extends DeploymentSummary {
  firmware_image_id: string | null;
  window_start: string | null;
  window_end: string | null;
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

export interface FirmwareImage {
  id: string;
  vendor: string;
  platform: string;
  version: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  vendor_sha256: string | null;
  vendor_sha512?: string | null;
  integrity_verified: boolean;
  /** Written reason for approving without the vendor's checksum (D-062). */
  unverified_reason?: string | null;
  compatible_models: string[];
  min_from_version: string | null;
  release_notes: string;
  status: 'uploaded' | 'approved' | 'retired';
  approved_by: string | null;
  approved_at: string | null;
  created_by: string;
  created_at: string;
}

export interface Compatibility {
  device_id: string;
  device_name: string;
  compatible: boolean;
  issues: Issue[];
}

export interface TopologyNode {
  device_id: string;
  name: string;
  category: string;
  manufacturer: string;
  model: string;
  environment: DeviceEnvironment;
  x: number | null;
  y: number | null;
}

export interface TopologyLink {
  id: string;
  a_device_id: string;
  a_interface: string;
  b_device_id: string;
  b_interface: string;
  mode: 'access' | 'trunk' | 'routed';
  vlans: number[];
  notes: string;
}

export type TopologyLinkInput = Omit<TopologyLink, 'id'>;

export interface Topology { nodes: TopologyNode[]; links: TopologyLink[]; issues: Issue[] }

export interface BootstrapProfile {
  vlan_id: number;
  vlan_name: string;
  untagged_port: string;
  address: string; // CIDR, e.g. "192.168.1.1/24"
}

export interface SerialPort { port: string; description: string; hardware_id: string }

export interface BootstrapPreview { supported: boolean; commands: string[]; notes: string[] }

export interface BootstrapResult {
  status: 'bootstrapped' | 'already_configured' | 'refused' | 'failed';
  message: string;
  commands_sent: string[];
  findings: string[];
  verified: boolean;
  saved: boolean;
  transcript: string;
  sanitized_transcript: string;
  /** A new switch's mandatory first-login credentials were set to the device's login. */
  credentials_set?: boolean;
  /** Hostname of the preconfigured configuration that was erased first, if any. */
  erased?: string;
  /** The switch asked for no password and none was set: it has no manager password. */
  no_password?: boolean;
  /** The switch had no manager password; UNDM set the device's login (confirmed). */
  password_set?: boolean;
  network_reachable: boolean | null;
  network_hint: string;
}

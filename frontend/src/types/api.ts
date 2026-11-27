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
  /** Staging of the system finished (D-108): when and by whom; null while open. */
  staged_at?: string | null;
  staged_by?: string;
  /** The zone its files are generated for (D-111): 1-128. */
  zone?: number | null;
  /** Its system, e.g. B007 (D-114): the modem's and BBU's files depend on it. */
  system_id?: string | null;
  /** Where UNDM reaches its devices (D-125): on the bench, or in the network through its BFW. */
  reached_via?: ReachedVia;
  /** The device that is its BFW (the FortiGate the laptop is connected to in the network). */
  network_gateway_id?: string | null;
  created_at: string;
  updated_at: string;
}

export type ReachedVia = 'bench' | 'network';

/** How UNDM reaches a device now (D-125): its address, port and driver there. */
export interface DeviceConnection {
  via: ReachedVia;
  address: string;
  port: number | null;
  driver_id: string;
  capabilities: string[];
  /** Why UNDM cannot reach it there (no network address yet). */
  problem: string | null;
}

/** An address a device's file gives it (D-125), read offline, with where in the file. */
export interface FileAddressCandidate {
  address: string; prefix: number | null; where: string; line: number; vdom: string | null;
  allows: string; file: string; version_id: string; on_bench: boolean;
}
export interface FileManagerRange { first: string; last: string; text: string; line: number; file: string }
export interface FileAddresses {
  files: { version_id: string; name: string; loaded: boolean; created_at: string }[];
  /** False: no reader for this device's files (the person types the address). */
  reader: boolean;
  addresses: FileAddressCandidate[];
  /** The addresses its file allows to manage it. */
  managers: FileManagerRange[];
  suggested: string | null;
  reason: string;
  /** This PC's own address towards it now, and whether its file's limits allow it. */
  pc_address: string | null;
  pc_allowed: boolean | null;
  /** A route command for this PC, shown only (UNDM never changes the PC's network). */
  route_hint: string | null;
}

/** Ping and traceroute answers (D-128); a simulated target starts no program. */
export interface PingAnswer {
  source: string; target: string; sent: number; received: number; rtt_ms: number[];
  simulated: boolean; raw: string; note: string; answered: boolean; target_device: string | null;
}
export interface HopAnswer {
  n: number; address: string | null; rtt_ms: (number | null)[]; timed_out: boolean;
  /** The system's device with this address; candidates when several share it. */
  device_id: string | null; interface: string | null; candidates: string[];
}
export interface TraceAnswer {
  source: string; target: string; hops: HopAnswer[]; reached: boolean; simulated: boolean;
  raw: string; note: string; target_device: string | null;
}
export interface CheckAllRow {
  device_id: string; address: string; via: ReachedVia; state: 'answers' | 'no_answer' | 'simulated' | 'no_address';
  sent?: number; received?: number | null; rtt_ms?: number[]; port?: number; port_open?: boolean; note?: string;
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
  /** The PC's serial port for a device reached over its console only (D-116). */
  console_port?: string | null;
  /** The console speed chosen for its console window (D-126); null: its model's own. */
  console_speed?: number | null;
  /** Its address in the network after staging (D-125); management_address stays its bench address. */
  network_address?: string | null;
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
  /** How UNDM reaches it now; absent in older answers (then: on the bench). */
  connection?: DeviceConnection | null;
  created_at: string;
  updated_at: string;
}

export type DeviceInput = Partial<Omit<Device, 'id' | 'project_id' | 'created_at' | 'updated_at' | 'connection' | 'network_address'>>;

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
  /** Its model's documented console speed and where it comes from (D-126). */
  console_speed?: number | null;
  console_speed_source?: string;
  /** The driver that reaches the same model in the network after staging (D-125). */
  network_driver_id?: string | null;
}

/** One login for all systems made from systems' own logins (D-115). Never a password. */
export interface SharedLoginGroup {
  /** The login kept. */ id: string;
  /** Suggested name, or the name of the login for all systems it joins. */ name: string;
  existing: boolean;
  members: { id: string; name: string; system: string; devices: number }[];
  devices: number;
}

export interface SharedLoginsResult {
  logins: SharedLoginGroup[];
  /** Logins that became one: old id -> the id that replaces it. */ replaced: Record<string, string>;
}

export interface CredentialRef {
  id: string;
  name: string;
  provider: 'keyring' | 'env';
  locator: string;
  has_secret: boolean | null;
  /** A login without a password (factory logins); the value itself is never sent. */
  empty_password?: boolean | null;
  /** A login for all systems (Settings → Logins), D-105. */
  shared?: boolean;
}

/** Default logins per device kind: ids of logins for all systems (D-105). */
export interface LoginDefaults {
  firewall: { login: string | null; login_after: string | null; tunnel_key: string | null };
  blackbox: { login: string | null; login_after: string | null };
  aruba: { login: string | null; current: string | null };
  /** The 7705 SAR-Hmc's approved login (D-124); missing in answers from before v94. */
  modem: { login: string | null };
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
  kind: 'configuration' | 'firmware' | 'first_login' | 'free_address' | 'restart' | 'license';
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
  /** D-088: needs attention and still waits for a person (else why not, below). */
  needs_attention?: boolean;
  /** "checked", or "superseded:<id of the later successful plan>". */
  attention_cleared?: string | null;
}

/** One device: step 1 restores the base file (replace), step 2 loads the site file (merge). */
export interface StagingPlan {
  staging_id: string;
  steps: Deployment[];
}

/** One step of a device's staging plan, as sent to UNDM (D-085). */
export interface StagingStepInput {
  kind: 'first_login' | 'firmware' | 'configuration' | 'free_address' | 'license';
  /** free_address: the other device of the system to take off its address (D-107). */
  other_device_id?: string;
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

export interface OperationResult { status: string; message: string; data: unknown; login_refused?: boolean }

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

/** What a console procedure running on a device is doing (D-112). */
export interface ConsoleProgress { running: boolean; stage: string | null; seconds: number; received: number; last_line: string }

export interface BootstrapPreview { supported: boolean; commands: string[]; notes: string[]; procedure?: 'management_vlan' | 'first_access' }

export interface BootstrapResult {
  status: 'bootstrapped' | 'already_configured' | 'refused' | 'failed';
  message: string;
  commands_sent: string[];
  findings: string[];
  verified: boolean;
  saved: boolean;
  transcript: string;
  sanitized_transcript: string;
  /** What the device said about itself (name, type, version), where the procedure reads it. */
  facts?: Record<string, string>;
  /** How the console behaved (masked): raw characters at the question, ignored control characters. */
  diagnostics?: Record<string, string>;
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

/** Team templates for all systems (D-111). */
export type TemplateRole = 'fortigate_base' | 'fortigate_site' | 'bhdmz' | 'lte' | 'tetra' | 'modem' | 'bbu_scf';
export interface ConfigTemplate {
  id: string;
  role: TemplateRole;
  version: string;
  filename: string;
  reference_zone: number | null;
  /** For files that also depend on the system (D-114). */
  reference_system?: string | null;
  counts: Record<string, number>;
  verified_zone: number | null;
  verified_system?: string | null;
  /** The team file's formatting, kept byte for byte on download (v83). */
  line_ending: 'lf' | 'crlf';
  final_newline: boolean;
  created_by: string;
  created_at: string;
  older: number;
}
export interface TemplateFile { filename: string; text: string; zone?: number | null; system?: string | null }
/** The team's PCI table (D-114): which table is in use, not its rows. */
export interface PciMapping { filename: string; sha256: string; imported_at: string | null; imported_by: string; systems: number; cells: number }
export interface GeneratedFile {
  role: TemplateRole; device_id: string; version_id: string; filename: string;
  template_version: string; verified_zone: number | null;
}
export interface ComparedFile {
  role: TemplateRole; device_id: string; generated_name: string; file_name: string | null;
  same: boolean; lines: number; differences: [number, string, string][];
}

/** Guided staging (D-117): a step a person does in the device's own portal. */
export interface GuidedStepState {
  key: string;
  title: string;
  detail: string;
  kind: 'check' | 'software' | 'file' | 'manual';
  note_label: string;
  done_by: string | null;
  done_at: string | null;
  note: string;
  file_name: string | null;
  file_sha256: string | null;
}

export interface Guided {
  procedure: string;
  title: string;
  steps: GuidedStepState[];
}

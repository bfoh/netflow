/**
 * Words shown to people. Internal values (states, driver ids, platform ids, fact keys) are
 * translated here, in one place, so every page uses the same plain wording (D-123).
 *
 * Glossary (one word for each thing; tests/conventions.test.ts keeps the synonyms out):
 * - a *device* is one switch, firewall, modem or BBU; a *system* (internally a project) is
 *   the set of devices staged together;
 * - a *plan* (internally a deployment) is one approved piece of work on devices; a *staging
 *   plan* is a device's plans in order; each is a *step*;
 * - a plan goes: Check and preview → Approve → Device check → Back up → Change → Verify;
 * - a *login* (internally a credential) is a user name and password kept in Windows
 *   Credential Manager; a *file* is a configuration file; a *complete file* replaces the
 *   configuration, *additions* add to it;
 * - *console setup* is the first setup over the console cable (a modem's is its *first
 *   access*); *read information* reads a device's facts; *back up now* saves its
 *   configuration in UNDM; the *backup slot* is a device's second firmware image;
 * - a system is reached *on the bench* (each device at its *bench address*, while it is
 *   staged) or *in the network* (after staging, each device at its *network address*,
 *   through the system's *BFW*, the FortiGate this PC is connected to), D-125.
 */
import type { Driver } from '../types/api';

const STATES: Record<string, { label: string; color: string; hint?: string }> = {
  // plans
  draft: { label: 'Draft', color: 'gray' },
  validating: { label: 'Checking', color: 'blue' },
  awaiting_approval: { label: 'Waiting for approval', color: 'orange', hint: 'Checked and ready to be approved.' },
  ready: { label: 'Approved', color: 'cyan', hint: 'Approved: it can be run.' },
  preflight: { label: 'Checking the device', color: 'blue' },
  backing_up: { label: 'Backing up', color: 'blue' },
  deploying: { label: 'Running', color: 'blue' },
  verifying: { label: 'Verifying', color: 'blue' },
  recovering: { label: 'Recovering', color: 'orange' },
  succeeded: { label: 'Succeeded', color: 'teal' },
  failed: { label: 'Failed', color: 'red', hint: 'Stopped before any device was changed, unless the events say otherwise.' },
  rolled_back: { label: 'Undone', color: 'orange', hint: 'Did not complete; the device was put back as it was.' },
  recovery_required: { label: 'Needs attention', color: 'red', hint: 'A device may be half-changed: read the events and check it.' },
  cancelled: { label: 'Cancelled', color: 'gray' },
  // devices in a plan
  pending: { label: 'Waiting', color: 'gray' },
  previewed: { label: 'Previewed', color: 'cyan' },
  preview_failed: { label: 'Preview failed', color: 'red' },
  preflight_passed: { label: 'Checked', color: 'cyan' },
  preflight_failed: { label: 'Check failed', color: 'red' },
  backed_up: { label: 'Backed up', color: 'cyan' },
  backup_failed: { label: 'Backup failed', color: 'red' },
  applied: { label: 'Applied', color: 'cyan' },
  apply_failed: { label: 'Failed', color: 'red' },
  verified: { label: 'Verified', color: 'teal' },
  verify_failed: { label: 'Verification failed', color: 'red' },
  no_change: { label: 'No change needed', color: 'teal' },
  skipped: { label: 'Skipped', color: 'gray' },
  rollback_failed: { label: 'Undo failed', color: 'red' },
  manual_recovery_required: { label: 'Needs attention', color: 'red' },
  // devices
  never_deployed: { label: 'Not staged yet', color: 'gray' },
  in_sync: { label: 'Up to date', color: 'teal' },
  drifted: { label: 'Changed on the device', color: 'yellow' },
  deployment_failed: { label: 'Last plan failed', color: 'red' },
  unknown: { label: 'Unknown', color: 'yellow' },
  planned: { label: 'Planned', color: 'gray' },
  factory_default: { label: 'Factory default', color: 'gray' },
  bootstrapped: { label: 'Console setup done', color: 'cyan' },
  managed: { label: 'Configured', color: 'teal' },
  decommissioned: { label: 'Decommissioned', color: 'gray' },
  // events and results
  ok: { label: 'OK', color: 'teal' },
  success: { label: 'OK', color: 'teal' },
  warning: { label: 'Warning', color: 'orange' },
  error: { label: 'Error', color: 'red' },
  unsupported: { label: 'Not supported', color: 'yellow' },
  // firmware images
  uploaded: { label: 'Uploaded', color: 'blue' },
  approved: { label: 'Approved', color: 'teal' },
  retired: { label: 'Retired', color: 'gray' },
};

/** A readable form of any snake_case value not in the list. */
export function humanize(value: string): string {
  const text = value.replaceAll('_', ' ').replaceAll('.', ' · ').trim();
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

export function stateLabel(state: string): string {
  return STATES[state]?.label ?? humanize(state);
}

export function stateColor(state: string): string {
  return STATES[state]?.color ?? 'gray';
}

export function stateHint(state: string): string | undefined {
  return STATES[state]?.hint;
}

const DRIVERS: Record<string, string> = {
  'ssh.aruba.aos_switch': 'ArubaOS-Switch over SSH',
  'ssh.aruba.aoscx': 'Aruba AOS-CX over SSH',
  'ssh.fortinet.fortios': 'FortiGate (FortiOS) over SSH',
  'ssh.blackbox.lig1014a': 'Black Box LIG1014A over SSH',
  'ssh.cisco.iosxe': 'Cisco IOS-XE over SSH',
};

/** How UNDM talks to a device, in words (never the internal driver id). */
export function driverLabel(driverId: string, drivers?: Driver[]): string {
  if (DRIVERS[driverId]) return DRIVERS[driverId];
  const d = drivers?.find((x) => x.driver_id === driverId);
  if (d?.simulated || driverId.startsWith('mock.')) return `Simulated ${d?.os_family ?? 'device'} (no real device)`;
  if (d) return `${d.os_family} over ${d.transport.toUpperCase()}`;
  return humanize(driverId.split('.').slice(1).join(' '));
}

const PLATFORMS: Record<string, string> = {
  aos_switch: 'ArubaOS-Switch (2930F)', aoscx: 'Aruba AOS-CX', fortios: 'FortiGate (FortiOS)',
  iosxe: 'Cisco IOS-XE', blackbox_lig1014a: 'Black Box LIG1014A', flexi_sbts: 'Nokia Flexi BBU (SBTS)',
};

export function platformLabel(platform: string): string {
  return PLATFORMS[platform] ?? humanize(platform);
}

/** What a plan step does, in one or two words: the same everywhere (wizard, report, plans). */
export function stepName(kind: string, applyMode: string): string {
  switch (kind) {
    case 'first_login': return 'First login';
    case 'firmware': return 'Firmware';
    case 'free_address': return 'Make room';
    case 'license': return 'License';
    case 'restart': return 'Restart';
    default: return applyMode === 'replace' ? 'Complete file' : 'Additions';
  }
}

/** Plan type, for lists and titles. */
export function planKind(d: { kind: string; apply_mode: string; dry_run: boolean }): string {
  const base = d.kind === 'firmware' ? 'Firmware upgrade'
    : d.kind === 'first_login' ? 'First login'
    : d.kind === 'free_address' ? 'Make room'
    : d.kind === 'restart' ? 'Restart'
    : d.kind === 'license' ? 'License file'
      : d.apply_mode === 'replace' ? 'Configuration (complete file)' : 'Configuration (additions)';
  return base + (d.dry_run ? ' · dry run' : '');
}

/** The steps every plan goes through, as shown on a plan's page. */
export const PLAN_STAGES = ['Check and preview', 'Approve', 'Device check', 'Back up', 'Change', 'Verify', 'Done'] as const;

export function applyModeLabel(mode: string): string {
  return mode === 'replace' ? 'complete file (replaces the configuration)' : 'additions (nothing is removed)';
}

const FACTS: Record<string, string> = {
  hostname: 'Hostname', vendor: 'Vendor', model: 'Model', os_version: 'Firmware version',
  serial_number: 'Serial number', mac_address: 'MAC address', identity: 'Identified by',
  port_count: 'Ports', active_image: 'Active firmware image', alternate_image: 'Backup firmware image',
  product_number: 'Product number', vdom_mode: 'VDOM mode', uptime: 'Uptime',
};

/** Facts shown to people, in this order; anything else goes under "Technical details". */
export const MAIN_FACTS = ['hostname', 'model', 'os_version', 'serial_number', 'mac_address', 'identity',
  'port_count', 'active_image', 'alternate_image', 'vendor'];

export function factLabel(key: string): string {
  return FACTS[key] ?? humanize(key);
}

const CAPABILITIES: Record<string, string> = {
  supports_ssh: 'Reach it over SSH',
  supports_configuration_backup: 'Back up its configuration',
  supports_configuration_apply: 'Change its configuration',
  supports_configuration_replace: 'Load a complete configuration file',
  supports_configuration_checkpoint: 'Save a named revision on the device',
  supports_firmware_upgrade: 'Upgrade its firmware',
  supports_firmware_secondary_image: 'Write the backup firmware slot',
  supports_reboot: 'Restart it',
  supports_first_login_setup: 'Set its password at the first login',
  supports_rest_api: 'Reach it over its REST API',
  supports_zero_touch_provisioning: 'Zero-touch provisioning',
  supports_serial_console: 'Use its serial console',
};

export function capabilityLabel(cap: string): string {
  return CAPABILITIES[cap] ?? humanize(cap.replace(/^supports_/, ''));
}

/** An audit action such as "deployment.execute.start" as words. */
/** Every action the backend writes to the audit log, in words (D-123). A test checks the
 *  backend's source, so a new action without words here fails. */
export const AUDIT_ACTIONS: Record<string, string> = {
  'config.generate': 'File generated from its settings', 'config.import': 'File imported',
  'credential.secret.set': 'Login password stored', 'credential_ref.create': 'Login added', 'credential_ref.delete': 'Login deleted',
  'credential_ref.share_all': 'Logins of the systems brought into Settings',
  'deployment.approve': 'Plan approved', 'deployment.cancel': 'Plan cancelled', 'deployment.checked': 'Plan marked as checked',
  'deployment.create': 'Plan made', 'deployment.delete': 'Plan deleted', 'deployment.execute': 'Plan run',
  'deployment.execute.error': 'Plan run ended with an error', 'deployment.execute.start': 'Plan started',
  'deployment.interrupted': 'Plan interrupted (UNDM stopped)', 'deployment.stop': 'Plan stopped',
  'deployment.stop_requested': 'Stop requested',
  'device.address_changed': 'Device address changed', 'device.console_port_set': 'Console port saved',
  'device.create': 'Device added', 'device.credential_changed': 'Device login changed', 'device.delete': 'Device deleted',
  'device.diagnostics.export': 'Diagnostics exported', 'device.intent.set': 'Intended settings saved',
  'device.license_stored': 'License file stored', 'device.management_port_off': 'Management port switched off (not saved)',
  'device.management_port_on': 'Management port on again', 'device.password_set': 'Device password set',
  'device.rename_skipped': 'Device not renamed (name in use)', 'device.renamed': 'Device renamed',
  'device.session_opened': 'SSH or console window opened', 'device.update': 'Device edited',
  'device.network_address_set': 'Network address set',
  'device.get_facts': 'Information read', 'device.check_reachability': 'Connection tested',
  'device.get_running_configuration': 'Configuration read', 'device.backup_configuration': 'Backed up',
  'device.get_firmware_information': 'Firmware read',
  'firmware.approve': 'Firmware image approved', 'firmware.delete': 'Firmware image deleted', 'firmware.retire': 'Firmware image retired',
  'firmware.upload': 'Firmware image uploaded', 'firmware.verify': 'Firmware checksum checked',
  'firmware_deployment.create': 'Firmware plan made',
  'guided.step_done': 'Step recorded (by hand)', 'guided.step_undone': 'Step undone (by hand)',
  'policy.change': 'Safety switch changed',
  'project.create': 'System created', 'project.delete': 'System deleted', 'project.seed': 'Example system added',
  'project.update': 'System edited',
  'provisioning.console_bootstrap': 'Console setup run', 'provisioning.console_identify': 'Name read over the console',
  'settings.certificate': 'Certificate answers saved', 'settings.defaults': 'Default logins saved',
  'settings.pci_mapping': 'PCI table imported',
  'staging.approve': 'Staging plan approved', 'staging.create': 'Staging plan made',
  'system.backups_export': 'Backups downloaded', 'system.bench_log': 'Bench log made', 'system.export': 'System exported',
  'system.import': 'System imported', 'system.reopened': 'Staging reopened', 'system.staged': 'Staging finished',
  'system.reached_via_changed': 'Moved between the bench and the network',
  'troubleshoot.ping': 'Ping', 'troubleshoot.traceroute': 'Traceroute', 'troubleshoot.check_all': 'Check all devices',
  'template.delete': 'Template deleted', 'template.files_export': 'Files downloaded from the templates',
  'template.import': 'Template imported',
  'topology.link.create': 'Link added', 'topology.link.delete': 'Link deleted', 'topology.link.update': 'Link edited',
};

export function auditActionLabel(action: string): string {
  return AUDIT_ACTIONS[action] ?? humanize(action);
}

const STAGES: Record<string, string> = {
  lifecycle: 'Status', validate: 'Check', preview: 'Preview', approve: 'Approval', preflight: 'Device check',
  backup: 'Backup', deploy: 'Change', verify: 'Verification', recover: 'Recovery', execute: 'Run',
};

/** The step of a plan an event belongs to. */
export function stageLabel(stage: string): string {
  return STAGES[stage] ?? humanize(stage);
}

/**
 * Words shown to people. Internal values (states, driver ids, platform ids, fact keys) are
 * translated here, in one place, so every page uses the same plain wording.
 *
 * Glossary: a *device* is one switch or firewall; a *system* (internally a project) is the
 * set of devices staged together; a *plan* is one approved piece of work on devices, run
 * in steps (internally a deployment).
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
  iosxe: 'Cisco IOS-XE', blackbox_lig1014a: 'Black Box LIG1014A',
};

export function platformLabel(platform: string): string {
  return PLATFORMS[platform] ?? humanize(platform);
}

/** Plan type, for lists. */
export function planKind(d: { kind: string; apply_mode: string; dry_run: boolean }): string {
  const base = d.kind === 'firmware' ? 'Firmware upgrade'
    : d.kind === 'first_login' ? 'First login'
      : d.apply_mode === 'replace' ? 'Configuration (complete file)' : 'Configuration (additions)';
  return base + (d.dry_run ? ' · dry run' : '');
}

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
export function auditActionLabel(action: string): string {
  const words: Record<string, string> = {
    'deployment.create': 'Plan created', 'deployment.approve': 'Plan approved', 'deployment.execute': 'Plan run',
    'deployment.execute.start': 'Plan started', 'deployment.cancel': 'Plan cancelled', 'deployment.stop': 'Plan stopped',
    'deployment.stop_requested': 'Stop requested', 'device.password_set': 'Device password set',
    'device.credential_changed': 'Device login changed', 'device.address_changed': 'Device address changed',
    'firmware.upload': 'Firmware image uploaded', 'firmware.approve': 'Firmware image approved',
    'firmware.verify': 'Firmware checksum checked', 'firmware.retire': 'Firmware image retired',
    'staging.create': 'Staging plan created', 'staging.approve': 'Staging plan approved',
    'policy.change': 'Safety switch changed', 'device.create': 'Device added', 'device.update': 'Device edited',
    'device.delete': 'Device deleted', 'project.create': 'System created', 'project.update': 'System edited',
    'project.delete': 'System deleted',
  };
  return words[action] ?? humanize(action);
}

const STAGES: Record<string, string> = {
  lifecycle: 'Status', validate: 'Check', preview: 'Preview', approve: 'Approval', preflight: 'Device check',
  backup: 'Backup', deploy: 'Change', verify: 'Verification', recover: 'Recovery', execute: 'Run',
};

/** The step of a plan an event belongs to. */
export function stageLabel(stage: string): string {
  return STAGES[stage] ?? humanize(stage);
}

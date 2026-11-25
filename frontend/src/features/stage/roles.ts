/**
 * The four devices of a system, by role (staging use case, docs/requirements). Addresses are
 * the bench defaults of docs/requirements/staging-run-design.md; they can be changed per device.
 */
import type { Device } from '../../types/api';

export type RoleKey = 'firewall' | 'blackbox' | 'aruba_a' | 'aruba_b';
export type StepKind = 'console' | 'first_login' | 'firmware' | 'base' | 'site' | 'file';

export interface Role {
  key: RoleKey;
  title: string;
  /** Model as listed in the device catalog. */
  model: string;
  modelId: string;
  realDriver: string;
  simulatedDriver: string;
  nameSuffix: string;
  address: string;
  /** The steps of this device, in order. */
  steps: StepKind[];
  hint: string;
  /** How it is cabled on the bench (docs/requirements/staging-run-design.md). */
  cable: string;
  /** Its management address once its file is loaded, as the team's files set it. */
  addressAfter: string;
  /** Why a real device of this role needs a 'login after loading' (its file sets a password
   * that its starting login does not have); absent when its starting login stays valid. */
  loginAfter?: string;
}

export const ROLES: Role[] = [
  { key: 'firewall', title: 'FortiGate 101F', model: 'FortiGate-101F', modelId: 'fortinet-fg-101f',
    realDriver: 'ssh.fortinet.fortios', simulatedDriver: 'mock.fortinet.fortios', nameSuffix: 'fw',
    address: '192.168.1.99', steps: ['first_login', 'firmware', 'base', 'site'],
    hint: 'Mgmt port, factory address. A new unit gets its approved password at the first login.',
    cable: 'MGMT port → small switch', addressAfter: '192.168.1.99',
    loginAfter: 'its base file sets its own admin password: choose the login with that password' },
  { key: 'blackbox', title: 'Black Box LIG1014A', model: 'LIG1014A', modelId: 'blackbox-lig1014a',
    realDriver: 'ssh.blackbox.lig1014a', simulatedDriver: 'mock.blackbox.switch', nameSuffix: 'bb',
    address: '192.0.2.1', steps: ['firmware', 'file'],
    hint: 'Factory address, user admin with no password. Firmware first, then the team file.',
    cable: 'Port 1/3 → small switch (its file keeps management on that port only)', addressAfter: '192.0.2.1',
    loginAfter: 'its team file sets the approved password: choose the approved login' },
  { key: 'aruba_a', title: 'Aruba 2930F (OOBM port 2)', model: '2930F', modelId: 'aruba-2930f',
    realDriver: 'ssh.aruba.aos_switch', simulatedDriver: 'mock.aruba.aos_switch', nameSuffix: 'sw-a',
    address: '192.168.1.1', steps: ['console', 'firmware', 'file'],
    hint: 'Console cable first: the console setup gives it this address on port 2.',
    cable: 'USB console cable first; after its console setup, port 2 → small switch', addressAfter: '192.168.1.1' },
  { key: 'aruba_b', title: 'Aruba 2930F (OOBM port 3)', model: '2930F', modelId: 'aruba-2930f',
    realDriver: 'ssh.aruba.aos_switch', simulatedDriver: 'mock.aruba.aos_switch', nameSuffix: 'sw-b',
    address: '192.168.1.2', steps: ['console', 'firmware', 'file'],
    hint: 'Temporary address so both switches fit on the bench; its file sets the final one.',
    cable: 'USB console cable first; after its console setup, port 3 → small switch', addressAfter: '192.168.1.1' },
];

export const STEP_WORDS: Record<StepKind, string> = {
  console: 'Console setup', first_login: 'First login', firmware: 'Firmware',
  base: 'Base file', site: 'Site file', file: 'Team file',
};

/** Rough durations seen on the bench, to set expectations (not limits). */
export const STEP_TIME: Record<StepKind, string> = {
  console: '2–8 min', first_login: '1 min', firmware: '5–10 min', base: '3–5 min', site: '2–5 min', file: '3–5 min',
};

/** The device of a system that plays a role: by name suffix, else the n-th device of the model. */
export function deviceForRole(role: Role, devices: Device[], taken: Set<string>): Device | undefined {
  const sameModel = devices.filter((d) => d.model === role.model && !taken.has(d.id));
  return sameModel.find((d) => d.name.endsWith(`-${role.nameSuffix}`)) ?? sameModel[0];
}

/** Devices for all roles at once, each device used once: by name, by address, then in order. */
export function assignRoles(devices: Device[]): Partial<Record<RoleKey, Device>> {
  const taken = new Set<string>();
  const out: Partial<Record<RoleKey, Device>> = {};
  // The role the wizard gave the device when it added it: survives a rename to the real
  // hostname (D-094) and the two 2930F ending at one address.
  for (const role of ROLES) {
    const byRole = devices.find((d) => d.model === role.model && d.role === role.title && !taken.has(d.id));
    if (byRole) { out[role.key] = byRole; taken.add(byRole.id); }
  }
  // Named matches next, so 'sw-b' is not taken by role A.
  for (const role of ROLES) {
    if (out[role.key]) continue;
    const named = devices.find((d) => d.model === role.model && d.name.endsWith(`-${role.nameSuffix}`) && !taken.has(d.id));
    if (named) { out[role.key] = named; taken.add(named.id); }
  }
  // Then by the role's bench address, then in order.
  for (const role of ROLES) {
    if (out[role.key]) continue;
    const byAddress = devices.find((d) => d.model === role.model && d.management_address === role.address && !taken.has(d.id));
    if (byAddress) { out[role.key] = byAddress; taken.add(byAddress.id); }
  }
  for (const role of ROLES) {
    if (out[role.key]) continue;
    const d = deviceForRole(role, devices, taken);
    if (d) { out[role.key] = d; taken.add(d.id); }
  }
  return out;
}

/**
 * The device already at the address this device's file moves it to (D-091). Both 2930F end at
 * the same address: the one still on its temporary address must wait until the other is
 * unplugged from the bench switch.
 */
export function addressTakenBy(role: Role, device: Device, all: { device: Device }[]): Device | undefined {
  if (device.management_address === role.addressAfter) return undefined;
  return all.map((x) => x.device).find((d) => d.id !== device.id && d.management_address === role.addressAfter
    && !temporaryAddress(d));
}

/** Where a device runs until its next power-on, if UNDM moved it aside (D-096). */
export function temporaryAddress(d: Device): string | undefined {
  const extra = (d.observed_facts as { extra?: { temporary_address?: string } } | null)?.extra;
  return extra?.temporary_address || undefined;
}

/** Spare bench address a device is moved to while another takes its address (D-096). */
export const SPARE_ADDRESS = '192.168.1.3';

/** Whether UNDM can move this device aside itself (real 2930F); else it must be unplugged. */
export const canMoveAside = (d: Device) => d.capabilities.includes('supports_temporary_address');

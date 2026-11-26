/**
 * The devices of a system, by role (staging use case, docs/requirements). Addresses are
 * the bench defaults of docs/requirements/staging-run-design.md; they can be changed per device.
 */
import type { Device, LoginDefaults } from '../../types/api';

export type RoleKey = 'firewall' | 'blackbox' | 'aruba_a' | 'aruba_b' | 'modem';
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
  /** 2930F: the port its console setup puts in the management VLAN (the bench cabling). */
  consolePort?: string;
  /** What this role's console step is called, when it is not the 2930F's console setup. */
  consoleWords?: string;
  /** Reached over its console cable only (the modem): no network address; its plan runs over
   * the console port saved on the device (D-116). */
  consoleCable?: boolean;
  /** What its file is, when it is not a switch's team file. */
  fileWords?: string;
  /** Its file sets the password of its own login (the modem's comes from the login): no
   * "login after loading". */
  fileKeepsLogin?: boolean;
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
    cable: 'USB console cable first; after its console setup, port 2 → small switch', addressAfter: '192.168.1.1',
    consolePort: '2' },
  { key: 'aruba_b', title: 'Aruba 2930F (OOBM port 3)', model: '2930F', modelId: 'aruba-2930f',
    realDriver: 'ssh.aruba.aos_switch', simulatedDriver: 'mock.aruba.aos_switch', nameSuffix: 'sw-b',
    address: '192.168.1.2', steps: ['console', 'firmware', 'file'],
    hint: 'Temporary address so both switches fit on the bench; its file sets the final one.',
    cable: 'USB console cable first; after its console setup, port 3 → small switch', addressAfter: '192.168.1.1',
    consolePort: '3' },
  // Console cable only: no bench address. Its first access (D-112), then its file over the same
  // console port by a plan (D-116).
  { key: 'modem', title: 'Nokia 7705 SAR-Hmc (modem)', model: '7705 SAR-Hmc', modelId: 'nokia-7705-sar-hmc',
    realDriver: 'console.nokia.sar', simulatedDriver: 'mock.nokia.sar', nameSuffix: 'modem',
    address: '', steps: ['console', 'file'], consoleCable: true, fileKeepsLogin: true,
    fileWords: "The modem's configuration file (Generate above makes it from its template), loaded over its console line by line.",
    hint: 'Console cable only. Its first access starts it once without its factory configuration and sets the admin password.',
    cable: 'USB console cable only (speed 115200); no network cable on the bench', addressAfter: '',
    consoleWords: 'First access (console)' },
];


/** Console steps done: the device has been set up over its console. */
export const CONSOLE_DONE = new Set(['bootstrapped', 'managed']);

/** The wizard role a device was added for (Stage a system sets `device.role`). */
export function roleOf(device: Device): Role | undefined {
  return ROLES.find((r) => r.title === device.role && r.model === device.model);
}

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
 * the same address: the one still on its first address must wait until the other is
 * unplugged from the bench switch.
 */
export function addressTakenBy(role: Role, device: Device, all: { device: Device }[]): Device | undefined {
  if (device.management_address === role.addressAfter) return undefined;
  return all.map((x) => x.device).find((d) => d.id !== device.id && d.management_address === role.addressAfter
    && !portOff(d));
}

/** The management port UNDM switched off, unsaved, until the device's next power-on (D-107). */
export function portOff(d: Device): string | undefined {
  const extra = (d.observed_facts as { extra?: { management_port_off?: { port?: string } } } | null)?.extra;
  return extra?.management_port_off?.port || undefined;
}

/** Whether UNDM can take this device off its address itself (real 2930F, D-107); else it
 *  must be unplugged. */
export const canMoveAside = (d: Device) => d.capabilities.includes('supports_management_port_off');

/** The defaults for all systems of a role's kind (both 2930F share one), D-105. */
export function roleDefaults(role: Role, d: LoginDefaults | undefined): {
  login: string | null; loginAfter: string | null; tunnelKey: string | null; current: string | null;
} {
  const none = { login: null, loginAfter: null, tunnelKey: null, current: null };
  if (!d?.firewall || !d.blackbox || !d.aruba) return none;
  if (role.key === 'firewall') return { ...none, login: d.firewall.login, loginAfter: d.firewall.login_after, tunnelKey: d.firewall.tunnel_key };
  if (role.key === 'blackbox') return { ...none, login: d.blackbox.login, loginAfter: d.blackbox.login_after };
  if (role.key === 'modem') return none; // no default login for the modem yet
  return { ...none, login: d.aruba.login, current: d.aruba.current };
}

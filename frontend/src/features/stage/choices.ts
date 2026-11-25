import type { Device, StagingStepInput } from '../../types/api';
import { canMoveAside, SPARE_ADDRESS } from './roles';
import type { Role, RoleKey } from './roles';

/** What the person chose for one device in the wizard. */
export interface Choice {
  firstLogin: boolean;
  imageId: string | null;
  allowDowngrade: boolean;
  alsoSecondary: boolean;
  baseId: string | null;
  siteId: string | null;
  fileId: string | null;
  /** Login valid once the base or team file is on the device (the file sets it). */
  loginAfter: string | null;
  /** Secret setting of the site file -> login holding its value. */
  secrets: Record<string, string>;
}

export const EMPTY_CHOICE: Choice = {
  firstLogin: true, imageId: null, allowDowngrade: false, alsoSecondary: false,
  baseId: null, siteId: null, fileId: null, loginAfter: null, secrets: {},
};

export type Choices = Partial<Record<RoleKey, Choice>>;

const key = (projectId: string) => `undm.stage.${projectId}`;

/** Choices are a convenience kept in this browser only; the plans made are the record. */
export function loadChoices(projectId: string): Choices {
  try {
    const raw = window.localStorage.getItem(key(projectId));
    return raw ? (JSON.parse(raw) as Choices) : {};
  } catch {
    return {};
  }
}

export function saveChoices(projectId: string, choices: Choices) {
  try {
    window.localStorage.setItem(key(projectId), JSON.stringify(choices));
  } catch {
    // storage unavailable: the choices last until the page is closed
  }
}

/** Whether a first login step applies: chosen, and the device can do it (real FortiGate). */
export function wantsFirstLogin(c: Choice, device?: Device): boolean {
  return c.firstLogin && (!device || device.capabilities.includes('supports_first_login_setup'));
}

/** The plan steps for a device, in its role's order; what is still missing, in words. */
export function planSteps(role: Role, c: Choice, device?: Device, inTheWay?: Device): { steps: StagingStepInput[]; missing: string[] } {
  const steps: StagingStepInput[] = [];
  const missing: string[] = [];
  for (const kind of role.steps) {
    if (kind === 'first_login' && wantsFirstLogin(c, device)) steps.push({ kind: 'first_login' });
    if (kind === 'firmware' && c.imageId) {
      steps.push({ kind: 'firmware', image_id: c.imageId, allow_downgrade: c.allowDowngrade, also_secondary: c.alsoSecondary });
    }
    if (kind === 'base') {
      if (c.baseId) {
        steps.push({ kind: 'configuration', version_id: c.baseId, ...(c.loginAfter ? { credential_after_ref_id: c.loginAfter } : {}) });
      } else missing.push('the base file');
    }
    if (kind === 'site') {
      if (c.siteId) {
        steps.push({ kind: 'configuration', version_id: c.siteId, ...(Object.keys(c.secrets).length ? { secrets: c.secrets } : {}) });
      } else missing.push('the site file');
    }
    if (kind === 'file') {
      if (c.fileId) {
        // Its file gives it an address another device of the system holds: that one is moved
        // to a spare address first, unsaved (D-096).
        if (inTheWay && canMoveAside(inTheWay)) {
          steps.push({ kind: 'free_address', other_device_id: inTheWay.id, address: SPARE_ADDRESS });
        }
        steps.push({ kind: 'configuration', version_id: c.fileId, ...(c.loginAfter ? { credential_after_ref_id: c.loginAfter } : {}) });
      } else missing.push('the team file');
    }
  }
  // A real device whose file sets a password its starting login does not have (D-092, bench
  // 2026-11-25: a Black Box plan without it loaded its file, then could not log in again).
  if (role.loginAfter && device && device.environment !== 'simulated' && (c.fileId || c.baseId) && !c.loginAfter) {
    missing.push(`the login after loading (${role.loginAfter.split(':')[0]})`);
  }
  return { steps, missing };
}

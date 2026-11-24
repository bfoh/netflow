import type { Device, StagingStepInput } from '../../types/api';
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
export function planSteps(role: Role, c: Choice, device?: Device): { steps: StagingStepInput[]; missing: string[] } {
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
        steps.push({ kind: 'configuration', version_id: c.fileId, ...(c.loginAfter ? { credential_after_ref_id: c.loginAfter } : {}) });
      } else missing.push('the team file');
    }
  }
  return { steps, missing };
}

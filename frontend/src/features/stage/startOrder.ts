import { RUNNING_STATES } from '../../hooks/queries';
import type { Device, StagingIndex, StagingStepInput } from '../../types/api';
import { type Choice, EMPTY_CHOICE, planSteps } from './choices';
import { addressTakenBy, CONSOLE_DONE, type Role } from './roles';

export interface StartItem {
  role: Role;
  device: Device;
  /** Started by "Start all ready" now. */
  ready: boolean;
  /** Why it waits (shown in the dialog). */
  reason?: string;
  /** Its plan that waits for approval or to run; none: a new plan is made. */
  stagingId?: string;
  /** The steps of a new plan. */
  steps: StagingStepInput[];
  /** Whether a firmware step will be approved (a window is needed). */
  firmware: boolean;
}

const OPEN = new Set(['awaiting_approval', 'ready']);

/**
 * Who "Start all ready" starts now and who waits, and why (D-121). Pure: decided from the
 * devices, the choices and their latest staging plans.
 * - A device already staged, or with its plan running, is left as it is.
 * - Its console work must be done, and nothing may be missing from its choices.
 * - A device whose file moves it to another device's address (switch B) waits until that
 *   device is staged.
 * - A last plan that ended without succeeding is not retried here: its card says why.
 * - The BBU is staged by hand (D-117): never started.
 */
export function startOrder(roles: { role: Role; device: Device }[], choices: Partial<Record<string, Choice>>,
  stagings: StagingIndex[]): StartItem[] {
  const latestOf = (d: Device) => stagings.find((x) => x.device_id === d.id);
  const staged = (d: Device) => { const l = latestOf(d); return !!l && l.states.length > 0 && l.states.every((s) => s === 'succeeded'); };
  const items: StartItem[] = [];
  for (const { role, device } of roles) {
    if (role.guided) continue;
    const latest = latestOf(device);
    if (staged(device)) continue;
    const choice = choices[role.key] ?? EMPTY_CHOICE;
    const taken = choice.fileId ? addressTakenBy(role, device, roles) : undefined;
    const { steps, missing } = planSteps(role, choice, device, taken);
    const wait = (reason: string): StartItem => ({ role, device, ready: false, reason, steps, firmware: false });
    if (latest?.states.some((s) => RUNNING_STATES.has(s))) { items.push(wait('its plan is running')); continue; }
    const open = latest && latest.states.some((s) => OPEN.has(s)) && latest.states.every((s) => OPEN.has(s) || s === 'succeeded');
    if (latest && !open) { items.push(wait('its last plan did not succeed: see its card')); continue; }
    if (role.steps.includes('console') && !CONSOLE_DONE.has(device.provisioning_status)) {
      items.push(wait(role.consoleCable ? 'its first access comes first' : 'its console setup comes first')); continue;
    }
    if (taken && !staged(taken)) { items.push(wait(`it starts once ${taken.name} is staged (same final address)`)); continue; }
    if (open) {
      items.push({ role, device, ready: true, stagingId: latest!.staging_id, steps: [],
        firmware: latest!.kinds.some((k, i) => k === 'firmware' && latest!.states[i] === 'awaiting_approval') });
      continue;
    }
    if (missing.length > 0) { items.push(wait(`still needed: ${missing.join(', ')}`)); continue; }
    if (steps.length === 0) { items.push(wait('nothing to do: no file or image chosen')); continue; }
    items.push({ role, device, ready: true, steps, firmware: steps.some((s) => s.kind === 'firmware') });
  }
  return items;
}

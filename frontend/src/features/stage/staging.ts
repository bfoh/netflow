import { RUNNING_STATES } from '../../hooks/queries';
import { stepName } from '../../services/labels';
import type { Deployment } from '../../types/api';

/** What a staging plan's steps allow now. */
export function stagingStatus(steps: Deployment[]) {
  const running = steps.some((s) => RUNNING_STATES.has(s.state));
  const pending = steps.filter((s) => s.state !== 'succeeded');
  return {
    running,
    canApprove: steps.some((s) => s.state === 'awaiting_approval'),
    canRun: !running && pending.length > 0 && pending.every((s) => s.state === 'ready'),
    done: steps.length > 0 && pending.length === 0,
    ended: !running && pending.some((s) => ['failed', 'recovery_required', 'rolled_back', 'cancelled'].includes(s.state)),
  };
}

/** A step in words: what it does to the device. */
export function stepTitle(step: Deployment): string {
  const what = step.kind === 'first_login'
    ? 'sets the device\'s password when the new unit asks for one'
    : step.kind === 'free_address'
      ? 'the other switch switches off its management port until its next power-on (nothing is saved on it)'
    : step.kind === 'license'
      ? 'the FortiGate fetches its license file from this PC and restarts with it'
    : step.kind === 'firmware'
      ? 'the device fetches the approved image from this PC and restarts into it'
      : step.apply_mode === 'replace'
        ? 'the device fetches it, restarts and comes back with it'
        : 'sent line by line (nothing is removed)';
  return `Step ${step.staging_step} · ${stepName(step.kind, step.apply_mode)}: ${what}`;
}

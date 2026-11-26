import { api } from '../../services/api';
import type { Policy } from '../../types/api';

/**
 * Staging alone (D-121, product owner): a firmware plan normally needs a second person to
 * approve it. The person who made it may approve it alone by ticking "I am staging alone": the
 * rule is switched off for that one approval and on again at once. Both changes are audited by
 * the server, and the Finish checklist checks that the rule is back on.
 *
 * Offered only when it is needed and possible: a firmware step waits, the person approving
 * made the plan, the rule is on, and it is not fixed in the start-up file.
 */
export function soloOffered(policy: Policy | undefined, { firmware, maker, actor }: {
  firmware: boolean; maker: string | undefined; actor: string;
}): boolean {
  return !!policy && firmware && maker === actor && policy.firmware_require_separate_approver === true
    && !(policy.locked ?? []).includes('firmware_require_separate_approver');
}

/** Whether a second person must approve and the person approving made the plan. */
export function needsSecondPerson(policy: Policy | undefined, { firmware, maker, actor }: {
  firmware: boolean; maker: string | undefined; actor: string;
}): boolean {
  return firmware && maker === actor && policy?.firmware_require_separate_approver !== false;
}

/** Runs `approve` with the second-approver rule off, and always switches it back on. If it
 *  cannot be switched back on, that is the error the person sees, whatever the approval did. */
export async function approveAlone<T>(approve: () => Promise<T>): Promise<T> {
  await api.changePolicy({ firmware_require_separate_approver: false });
  let outcome: { ok: true; value: T } | { ok: false; error: unknown };
  try {
    outcome = { ok: true, value: await approve() };
  } catch (error) {
    outcome = { ok: false, error };
  }
  try {
    await api.changePolicy({ firmware_require_separate_approver: true });
  } catch (e) {
    const why = e instanceof Error ? e.message : String(e);
    throw new Error(`${outcome.ok ? 'Approved, but the' : 'Not approved, and the'} rule “A second person approves firmware plans” `
      + `could not be switched back on (${why}). Turn it on in Settings → Safety before you go on.`);
  }
  if (!outcome.ok) throw outcome.error;
  return outcome.value;
}

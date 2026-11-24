import { api } from '../services/api';
import type { DeploymentSummary } from '../types/api';
import { useAction } from './queries';
import { useConfirm } from './useConfirm';

const RUNNING = new Set(['validating', 'preflight', 'backing_up', 'deploying', 'verifying', 'recovering']);

/** Delete a plan after a confirmation; a staging step takes its whole staging plan (D-088).
 *  Returns [askToDelete(plan, then?), dialog, canDelete(plan)]. */
export function usePlanDelete() {
  const [ask, dialog] = useConfirm();
  const del = useAction((id: string) => api.deleteDeployment(id), 'Plan deleted', { errorInDialog: true });
  const askToDelete = (d: Pick<DeploymentSummary, 'id' | 'state' | 'staging_id'>, then?: () => void) => ask({
    title: d.staging_id ? 'Delete this staging plan?' : 'Delete this plan?',
    confirmLabel: 'Delete',
    message: `${d.staging_id ? 'Every step of the staging plan is deleted with it. ' : ''}`
      + 'Its preview, results and events are removed from UNDM; the audit log keeps a record of what it was and who '
      + 'deleted it. The device is not touched'
      + `${d.state === 'recovery_required' ? ': if it may be half-changed, check it first.' : '.'}`,
    onConfirm: async () => { await del.mutateAsync(d.id); then?.(); },
  });
  const canDelete = (d: Pick<DeploymentSummary, 'state'>) => !RUNNING.has(d.state);
  return [askToDelete, dialog, canDelete] as const;
}

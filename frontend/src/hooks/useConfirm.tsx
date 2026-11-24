import { useState } from 'react';

import { ConfirmDialog, type ConfirmRequest } from '../components/ConfirmDialog';

/** One confirmation dialog for every destructive or device-changing action.
 *  Returns [ask, dialog]: call ask({...}) from a click and render the dialog once. */
export function useConfirm() {
  const [req, setReq] = useState<ConfirmRequest | null>(null);
  const dialog = req ? <ConfirmDialog key={req.title} req={req} onClose={() => setReq(null)} /> : null;
  return [setReq, dialog] as const;
}

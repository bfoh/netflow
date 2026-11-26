import { useCallback, useRef, useState } from 'react';

import { ConfirmDialog, type ConfirmRequest } from '../components/ConfirmDialog';

/** One confirmation dialog for every destructive or device-changing action.
 *  Returns [ask, dialog]: call ask({...}) from a click and render the dialog once.
 *  When it closes, focus goes back to what was focused when it opened (WCAG 2.4.3). */
export function useConfirm() {
  const [req, setReq] = useState<ConfirmRequest | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const ask = useCallback((r: ConfirmRequest | null) => {
    if (r) opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setReq(r);
  }, []);
  const close = useCallback(() => {
    setReq(null);
    const back = opener.current;
    opener.current = null;
    if (back) window.setTimeout(() => { if (back.isConnected) back.focus(); }, 0);
  }, []);
  const dialog = req ? <ConfirmDialog key={req.title} req={req} onClose={close} /> : null;
  return [ask, dialog] as const;
}

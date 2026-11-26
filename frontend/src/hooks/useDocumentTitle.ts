import { useEffect } from 'react';

export const APP_NAME = 'UNDM';

/** The browser tab says where you are (WCAG 2.4.2). */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}

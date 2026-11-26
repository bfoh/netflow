import type React from 'react';

/** Right-click on a row: open the menu of the "⋯" button in that row. */
export function openDeviceMenu(e: React.MouseEvent<HTMLElement>) {
  const button = e.currentTarget.querySelector<HTMLButtonElement>('[data-device-menu]');
  if (!button) return;
  e.preventDefault();
  // The menu closes on a press outside it: open it once the right button is released
  // (on Windows the right-click event comes after the release, elsewhere before it).
  const open = () => window.setTimeout(() => button.click(), 0);
  if (e.buttons & 2) window.addEventListener('mouseup', open, { once: true });
  else open();
}


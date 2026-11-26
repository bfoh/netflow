import type { Page } from '@playwright/test';

/** Opens a page from the sidebar by its label (D-120). The engineers' pages sit in the folded
 *  Advanced group: it is opened first when the entry is not shown. */
export async function openFromNav(page: Page, label: string) {
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const link = nav.getByRole('link', { name: label, exact: true });
  if (!(await link.isVisible())) await nav.getByRole('button', { name: 'Advanced' }).click();
  await link.click();
}

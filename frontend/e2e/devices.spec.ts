import { expect, test } from '@playwright/test';

/** The device menu on a simulated switch (D-099): right-click, Check information, Test, then its log.
 *  Fictional names, RFC 5737 address. */
test('device menu: check information, test, and the device log', async ({ page, request }) => {
  const id = String(Date.now()).slice(-6);
  const p = await (await request.post('/api/projects', { data: { name: `Menu ${id}`, purpose: 'Staging' } })).json();
  await request.post(`/api/projects/${p.id}/devices`, { data: {
    name: `menu-sw-${id}`, manufacturer: 'Aruba', model: '2930F', category: 'switch', os_family: 'ArubaOS-Switch',
    driver_id: 'mock.aruba.aos_switch', environment: 'simulated', management_address: '192.0.2.20' } });

  await page.goto(`/systems/${p.id}`);
  const row = page.getByRole('row', { name: new RegExp(`menu-sw-${id}`) });
  await row.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Check information' }).click();
  const info = page.getByRole('dialog', { name: `Information · menu-sw-${id}` });
  await expect(info.getByText('Firmware', { exact: false }).first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(info).toBeHidden();

  await row.getByRole('button', { name: `Actions for menu-sw-${id}` }).click();
  await page.getByRole('menuitem', { name: 'Test connection' }).click();
  await row.getByRole('button', { name: `Actions for menu-sw-${id}` }).click();
  await page.getByRole('menuitem', { name: 'Device log' }).click();
  await expect(page.getByRole('tab', { name: 'Log' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText(/Test connection|Check reachability/i).first()).toBeVisible();
});

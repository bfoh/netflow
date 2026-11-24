import { expect, test } from '@playwright/test';

/** Console bootstrap of a simulated ArubaOS-Switch through the Console setup page. */
test('console bootstrap on the simulated console: run, verify, re-run is a no-op', async ({ page }) => {
  const id = String(Date.now()).slice(-6);
  const name = `dmz-sw-${id}`;
  await page.goto('/projects');
  await page.getByRole('button', { name: 'New system' }).click();
  await page.getByLabel('System name').fill(`Bootstrap ${id}`);
  await page.getByRole('button', { name: 'Create system' }).click();

  await page.getByRole('button', { name: 'Add device' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', { name: 'Device model' }).click();
  await page.getByRole('option', { name: /Aruba 2930F/ }).click();
  await dialog.getByLabel('Device name').fill(name);
  await dialog.getByRole('button', { name: 'Add device' }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole('link', { name }).click();
  await page.getByRole('link', { name: 'Console bootstrap' }).click();
  await expect(page.getByRole('heading', { name: 'Console setup' })).toBeVisible();

  await page.getByLabel('Untagged port').fill('2');
  await page.getByLabel('Address / prefix').fill('192.168.1.2/24');
  await page.getByRole('button', { name: 'Preview commands' }).click();
  await expect(page.getByText('ip address 192.168.1.2 255.255.255.0')).toBeVisible();
  await expect(page.getByText('write memory', { exact: false }).first()).toBeVisible();

  const runBootstrap = async () => {
    await page.getByRole('button', { name: 'Run console bootstrap…' }).click();
    const modal = page.getByRole('dialog');
    await expect(modal.getByRole('button', { name: 'Run bootstrap' })).toBeDisabled();
    await modal.getByLabel(/Type the device name to confirm/).fill(name);
    await modal.getByRole('button', { name: 'Run bootstrap' }).click();
    await expect(modal).toBeHidden();
  };

  await runBootstrap();
  await expect(page.getByText('Bootstrap complete')).toBeVisible();
  await expect(page.getByText('read back and verified')).toBeVisible();
  await expect(page.getByText('saved (write memory)')).toBeVisible();
  await expect(page.getByText('<<< untagged 2')).toBeVisible();

  await runBootstrap();
  await expect(page.getByText('Already bootstrapped — nothing was changed')).toBeVisible();

  await page.getByRole('link', { name: 'Continue on the device page' }).click();
  await expect(page.getByText('192.168.1.2', { exact: true })).toBeVisible();
});

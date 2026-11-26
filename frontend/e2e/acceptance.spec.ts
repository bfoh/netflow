import { expect, test } from '@playwright/test';

import { openFromNav } from './helpers/nav';

/**
 * Directive section 28: first-prototype acceptance flow, through the UI.
 * Uses a unique project name so it can run repeatedly against the same database.
 */
test('create project, add devices, generate, deploy (simulated), audit', async ({ page }) => {
  const project = `E2E ${Date.now()}`;
  const suffix = String(Date.now()).slice(-6);
  const octet = Number(suffix.slice(-2)); // no leading zeros: "07" is not a valid IPv4 octet

  // 2. dashboard
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible();

  // 3. create project
  await openFromNav(page, 'Systems');
  await page.getByRole('button', { name: 'New system' }).click();
  await page.getByLabel('System name').fill(project);
  await page.getByLabel('Site or location').fill('Synthetic Site');
  await page.getByRole('button', { name: 'Create system' }).click();
  await expect(page.getByRole('heading', { name: project })).toBeVisible();

  // 4-5, 7. add an Aruba switch and a Fortinet firewall with metadata and roles
  const addDevice = async (model: RegExp, name: string, role: string, address: string) => {
    await page.getByRole('button', { name: 'Add device' }).first().click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox', { name: 'Device model' }).click();
    await page.getByRole('option', { name: model }).click();
    await dialog.getByLabel('Device name').fill(name);
    await dialog.getByLabel('Role', { exact: true }).fill(role);
    await dialog.getByLabel('Address', { exact: true }).fill(address);
    await dialog.getByRole('button', { name: 'Add device' }).click();
    await expect(dialog).toBeHidden();
  };
  await addDevice(/Aruba 6300M/, `sw-${suffix}`, 'access-switch', `10.200.${octet}.11`);
  await addDevice(/FortiGate-60F/, `fw-${suffix}`, 'edge-firewall', `10.200.${octet}.1`);

  // 6. both visible in the inventory
  await openFromNav(page, 'Devices (all systems)');
  await page.getByLabel('Search devices').fill(suffix);
  await expect(page.getByRole('link', { name: `sw-${suffix}` })).toBeVisible();
  await expect(page.getByRole('link', { name: `fw-${suffix}` })).toBeVisible();

  // 8-10. define VLAN + management intent, generate and preview the switch configuration
  await page.getByRole('link', { name: `sw-${suffix}` }).click();
  await page.getByRole('tab', { name: 'Intended settings' }).click();
  await page.getByRole('button', { name: 'Add VLAN' }).click();
  await page.getByLabel('VLAN ID').fill('99');
  await page.getByLabel('VLAN name').fill('mgmt');
  await page.getByRole('button', { name: 'Add interface' }).click();
  await page.getByLabel('Interface', { exact: true }).fill('vlan99');
  await page.getByLabel('Address', { exact: true }).fill(`10.200.${octet}.11/24`);
  await page.getByRole('button', { name: 'Save intent' }).click();
  await expect(page.getByText('Intent saved').last()).toBeVisible();
  await page.getByRole('tab', { name: 'Files' }).click();
  await page.getByRole('button', { name: 'Generate configuration' }).click();
  await expect(page.getByText('Validation passed')).toBeVisible();
  await expect(page.getByText('interface vlan 99')).toBeVisible();

  // firewall: management interface intent, generated through the same path
  await openFromNav(page, 'Devices (all systems)');
  await page.getByLabel('Search devices').fill(suffix);
  await page.getByRole('link', { name: `fw-${suffix}` }).click();
  await page.getByRole('tab', { name: 'Intended settings' }).click();
  await page.getByRole('button', { name: 'Add interface' }).click();
  await page.getByLabel('Interface', { exact: true }).fill('internal1');
  await page.getByLabel('Address', { exact: true }).fill(`10.200.${octet}.1/24`);
  await page.getByRole('button', { name: 'Save intent' }).click();
  await expect(page.getByText('Intent saved').last()).toBeVisible();
  await page.getByRole('tab', { name: 'Files' }).click();
  await page.getByRole('button', { name: 'Generate configuration' }).click();
  await expect(page.getByText(`set hostname "fw-${suffix}"`)).toBeVisible();

  // 11. simulated deployment plan with both devices
  await openFromNav(page, 'Plans');
  await page.getByRole('link', { name: 'New plan' }).click();
  await page.getByRole('combobox', { name: 'System' }).click();
  await page.getByRole('option', { name: project }).click();
  await page.getByLabel(`Include sw-${suffix}`).check();
  await page.getByLabel(`Include fw-${suffix}`).check();
  await page.getByRole('button', { name: 'Validate and preview' }).click();
  await expect(page.getByText('Waiting for approval').first()).toBeVisible();

  // 12-13. approve, execute, inspect progress and outcome
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await page.getByRole('button', { name: 'Run plan' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Plan succeeded')).toBeVisible();
  await expect(page.getByText('Verified', { exact: true })).toHaveCount(2);

  // 14. audit record
  await openFromNav(page, 'Audit log');
  await expect(page.getByText('deployment.execute', { exact: true }).first()).toBeVisible();
});

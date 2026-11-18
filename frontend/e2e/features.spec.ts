import { createHash } from 'node:crypto';

import { expect, type Page, test } from '@playwright/test';

/** Configuration import, topology links and a simulated firmware upgrade, through the UI. */
const nav = (page: Page, label: string) =>
  page.getByRole('navigation', { name: 'Main navigation' }).getByText(label, { exact: true }).click();

async function setActor(page: Page, name: string) {
  await nav(page, 'Settings');
  await page.getByLabel('Acting as').fill(name);
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole("banner").getByText(name, { exact: true })).toBeVisible();
}

test('import config, draw topology, upgrade firmware (simulated)', async ({ page }) => {
  const id = String(Date.now()).slice(-6);
  const project = `Features ${id}`;
  await page.goto('/');
  await setActor(page, 'e2e-engineer');

  await nav(page, 'Projects');
  await page.getByRole('button', { name: 'New project' }).click();
  await page.getByLabel('Project name').fill(project);
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: project })).toBeVisible();

  for (const [model, name, addr] of [[/Aruba 6300M/, `sw-${id}`, `10.201.${id.slice(-2)}.11`],
    [/FortiGate-60F/, `fw-${id}`, `10.201.${id.slice(-2)}.1`]] as const) {
    await page.getByRole('button', { name: 'Add device' }).first().click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox', { name: 'Device model' }).click();
    await page.getByRole('option', { name: model }).click();
    await dialog.getByLabel('Device name').fill(name);
    await dialog.getByLabel('Management address').fill(addr);
    await dialog.getByRole('button', { name: 'Add device' }).click();
    await expect(dialog).toBeHidden();
  }

  // Configuration import
  await page.getByRole('link', { name: `sw-${id}` }).click();
  await page.getByRole('tab', { name: 'Configurations' }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: 'switch-backup.cfg', mimeType: 'text/plain',
    buffer: Buffer.from(`hostname sw-${id}\r\nvlan 42\r\n    name imported\r\n`),
  });
  await expect(page.getByText(/Imported from/)).toBeVisible();
  await expect(page.getByText('vlan 42')).toBeVisible();

  // Topology: connect the two devices
  await nav(page, 'Topology');
  await page.getByRole('combobox', { name: 'Project' }).click();
  await page.getByRole('option', { name: project }).click();
  const sw = page.locator('.react-flow__node', { hasText: `sw-${id}` });
  const fw = page.locator('.react-flow__node', { hasText: `fw-${id}` });
  await expect(sw).toBeVisible();
  await sw.locator('.react-flow__handle-top').dragTo(fw.locator('.react-flow__handle-bottom'));
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(`Interface on sw-${id}`).fill('1/1/48');
  await dialog.getByLabel(`Interface on fw-${id}`).fill('internal1');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('1/1/48 ↔ internal1')).toBeVisible();
  await expect(page.getByText(/routed link: no address/)).toBeVisible();

  // Firmware: upload with vendor checksum, approve, plan
  const image = Buffer.from(`SYNTHETIC E2E IMAGE ${id}\n`.repeat(100));
  await nav(page, 'Firmware');
  await page.locator('input[type=file]').setInputFiles({ name: `cx-${id}.swi`, mimeType: 'application/octet-stream', buffer: image });
  await page.getByRole('textbox', { name: 'Version', exact: true }).fill('10.2.0');
  await page.getByRole('combobox', { name: 'Compatible models' }).fill('6300M');
  await page.getByRole('combobox', { name: 'Compatible models' }).press('Enter');
  await page.getByLabel('Vendor SHA-256').fill(createHash('sha256').update(image).digest('hex'));
  await page.getByRole('button', { name: 'Upload to repository' }).click();
  const row = page.getByRole('row', { name: new RegExp(`cx-${id}`) });
  await expect(row.getByText('verified')).toBeVisible();
  await row.getByRole('button', { name: 'Approve' }).click();
  await expect(row.getByText('approved', { exact: true })).toBeVisible();

  await page.getByRole('tab', { name: 'Upgrade planning' }).click();
  await page.getByRole('combobox', { name: 'Approved image' }).click();
  await page.getByRole('option', { name: new RegExp(`cx-${id}`) }).click();
  await page.getByRole('combobox', { name: 'Project' }).click();
  await page.getByRole('option', { name: project }).click();
  await page.getByLabel(`Upgrade sw-${id}`).check();
  await page.getByRole('button', { name: 'Check compatibility (offline)' }).click();
  await expect(page.getByText('compatible', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Create upgrade plan' }).click();
  await expect(page.getByText('awaiting approval').first()).toBeVisible();
  const planUrl = page.url();

  // A different person approves with a maintenance window, then executes.
  await setActor(page, 'e2e-approver');
  await page.goto(planUrl);
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await page.getByRole('button', { name: 'Approve with this window' }).click();
  await page.getByRole('button', { name: 'Execute deployment' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Deployment succeeded')).toBeVisible();
  await expect(page.getByText(/→ 10\.2\.0/)).toBeVisible();
});

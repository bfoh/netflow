import { expect, test } from '@playwright/test';

/** The Stage a system wizard on a simulated Black Box: new system, device, team file, plan, run, report.
 *  The file is SYNTHETIC (fictional name, RFC 5737 address). */
test('stage a system with the wizard (simulated Black Box)', async ({ page }) => {
  const id = String(Date.now()).slice(-6);
  const system = `Wizard ${id}`;
  await page.goto('/stage');
  await page.getByLabel('System name').fill(system);
  await page.getByRole('button', { name: 'Create and continue' }).click();
  await expect(page.getByRole('heading', { name: `Stage a system · ${system}` })).toBeVisible();

  await page.getByText('Practice (simulated)').click();
  const bbRole = page.locator('.mantine-Card-root', { hasText: 'Black Box LIG1014A' }).first();
  await bbRole.getByRole('button', { name: /Add it/ }).click();
  await expect(bbRole.getByRole('link', { name: `wizard-${id}-bb` })).toBeVisible();

  await page.getByRole('button', { name: 'Next: Files and firmware' }).click();
  await page.locator('input[type=file]').first().setInputFiles({
    name: `team-${id}.txt`, mimeType: 'text/plain',
    buffer: Buffer.from(`hostname e2e-bb-${id}\n!\nvlan 1001\n!\ninterface GigabitEthernet 1/3\n description Port-3\n!\n`
      + 'interface vlan 1\n ip address 192.0.2.1 255.255.255.0\n!\nend\n'),
  });
  await expect(page.getByText('Ready', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Next: Bench check' }).click();
  await expect(page.getByText('Cabling')).toBeVisible();
  await page.getByRole('button', { name: 'Next: Run' }).click();
  const card = page.locator('.mantine-Card-root', { hasText: `wizard-${id}-bb` });
  await card.getByRole('button', { name: 'Make the plan' }).click();
  await card.getByRole('button', { name: 'Approve all steps' }).click();
  await card.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(card.getByText('Staged')).toBeVisible({ timeout: 30_000 });

  await page.getByRole('button', { name: 'Next: Report' }).click();
  await expect(page.getByRole('heading', { name: `Staging report · ${system}` })).toBeVisible();
  await expect(page.locator('#staging-report').getByText('Succeeded')).toBeVisible();
});

import { expect, test } from '@playwright/test';

/** Nokia 7705 SAR-Hmc: first access on the simulated console (D-112), then its configuration file
 *  by a plan (D-116; the file is SYNTHETIC). Nothing is contacted.
 *  The login comes from the backend's environment (UNDM_CRED_E2E_MODEM_USERNAME=admin and
 *  UNDM_CRED_E2E_MODEM_PASSWORD, any made-up value of 8+ characters); without them the test
 *  is skipped, because a simulated first access still needs a login to set. */
test('first access of a simulated modem from the wizard, then its file by a plan', async ({ page, request }) => {
  const id = String(Date.now()).slice(-5);
  const p = await (await request.post('/api/projects', { data: { name: `E2E modem ${id}`, purpose: 'Staging' } })).json();
  const ref = await (await request.post(`/api/projects/${p.id}/credential-refs`,
    { data: { name: `approved-${id}`, provider: 'env', locator: 'e2e-modem' } })).json();
  test.skip(!ref.has_secret, 'the backend has no UNDM_CRED_E2E_MODEM_USERNAME / _PASSWORD');
  const name = `e2e-${id}-modem`;
  await request.post(`/api/projects/${p.id}/devices`, { data: {
    name, manufacturer: 'Nokia', model: '7705 SAR-Hmc', category: 'router', os_family: 'SR OS (7705 SAR)',
    driver_id: 'mock.nokia.sar', environment: 'simulated', role: 'Nokia 7705 SAR-Hmc (modem)', credential_ref_id: ref.id } });

  await page.goto(`/stage/${p.id}?step=3`);
  await expect(page.getByText('1. First access (console)')).toBeVisible();
  await page.getByRole('link', { name: 'Open console setup' }).click();
  await expect(page.getByText(/sros \(it counts down from 30 seconds\)/)).toBeVisible();
  await page.getByRole('button', { name: 'Run first access…' }).click();
  await page.getByLabel(/Type the device name to confirm/).fill(name);
  await page.getByRole('button', { name: 'Run first access', exact: true }).click();
  await expect(page.getByText('First access done', { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('admin password set')).toBeVisible();
  await expect(page.getByText('boot options and configuration saved')).toBeVisible();
  // The modem echoes the command line; the password is masked wherever it is shown.
  await expect(page.locator('body')).toContainText('password ********');
  await expect(page.locator('body')).not.toContainText(process.env.UNDM_CRED_E2E_MODEM_PASSWORD ?? 'Example-Only-Pass-77');
  // D-121: the first access ran inside the wizard; back to the Run step.
  await page.getByRole('button', { name: 'Back to Run' }).first().click();
  await expect(page.getByText('Done', { exact: true })).toBeVisible();

  // Its configuration file, chosen in step 2 and loaded by a plan in step 4.
  await page.goto(`/stage/${p.id}?step=1`);
  await page.locator('input[type=file]').first().setInputFiles({
    name: `LTEModem-${id}.txt`, mimeType: 'text/plain',
    buffer: Buffer.from(`exit all\nconfigure\n    system\n        name "e2e-modem-${id}"\n    exit\nexit all\n`),
  });
  await expect(page.getByText('Ready', { exact: true })).toBeVisible();
  await page.goto(`/stage/${p.id}?step=3`);
  await expect(page.getByText('2. Its configuration file (console)')).toBeVisible();
  const card = page.locator('.mantine-Card-root', { hasText: name });
  await card.getByRole('button', { name: 'Make the plan' }).click();
  await card.getByRole('button', { name: 'Approve all steps' }).click();
  await card.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(card.getByText('Staged')).toBeVisible({ timeout: 30_000 });
});

import { expect, test } from '@playwright/test';

/** Nokia 7705 SAR-Hmc: first access on the simulated console (D-112). Nothing is contacted.
 *  The login comes from the backend's environment (UNDM_CRED_E2E_MODEM_USERNAME=admin and
 *  UNDM_CRED_E2E_MODEM_PASSWORD, any made-up value of 8+ characters); without them the test
 *  is skipped, because a simulated first access still needs a login to set. */
test('first access of a simulated modem from the wizard', async ({ page, request }) => {
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
  await expect(page.getByText(/sros \(within 25 seconds\)/)).toBeVisible();
  await page.getByRole('button', { name: 'Run first access…' }).click();
  await page.getByLabel(/Type the device name to confirm/).fill(name);
  await page.getByRole('button', { name: 'Run first access', exact: true }).click();
  await expect(page.getByText('First access done', { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('admin password set')).toBeVisible();
  await expect(page.getByText('boot options and configuration saved')).toBeVisible();
  // The modem echoes the command line; the password is masked wherever it is shown.
  await expect(page.locator('body')).toContainText('password ********');
  await expect(page.locator('body')).not.toContainText(process.env.UNDM_CRED_E2E_MODEM_PASSWORD ?? 'Example-Only-Pass-77');
  await page.getByRole('link', { name: 'Back to Stage a system' }).click();
  await expect(page.getByText('First access done', { exact: true })).toBeVisible();
});

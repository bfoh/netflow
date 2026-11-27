import { createHash } from 'node:crypto';

import { expect, test } from '@playwright/test';

/** Nokia Flexi BBU on a simulated unit (D-117): the guided steps, recorded one by one. The package
 *  and the SCF are SYNTHETIC; nothing is contacted. */
test('the Flexi BBU is staged by hand with the guided steps', async ({ page, request }) => {
  const id = String(Date.now()).slice(-6);
  const p = await (await request.post('/api/projects', { data: { name: `E2E bbu ${id}`, purpose: 'Staging' } })).json();
  const name = `e2e-${id}-bbu`;
  const bbu = await (await request.post(`/api/projects/${p.id}/devices`, { data: {
    name, manufacturer: 'Nokia', model: 'FSMF', category: 'other', os_family: 'SBTS (Flexi Multiradio 10)',
    driver_id: 'mock.nokia.flexi', environment: 'simulated', role: 'Nokia Flexi BBU (FSMF)',
    management_address: '192.0.2.129', management_protocol: 'https_api', management_port: 443 } })).json();
  const pkg = Buffer.from(`synthetic package ${id}\n`.repeat(32));
  const img = await (await request.post('/api/firmware/images', { multipart: {
    vendor: 'Nokia', platform: 'flexi_sbts', version: `SBTS-E2E-${id}`, compatible_models: 'FSMF',
    vendor_sha256: createHash('sha256').update(pkg).digest('hex'),
    file: { name: `SBTS_E2E_${id}.zip`, mimeType: 'application/zip', buffer: pkg } } })).json();
  await request.post(`/api/firmware/images/${img.id}/approve`);
  const scf = await (await request.post(`/api/devices/${bbu.id}/configs/import`, { data: {
    filename: `scf_e2e_${id}.xml`, text: '<?xml version="1.0"?>\n<raml version="2.1"><cmData type="actual"/></raml>\n' } })).json();
  await page.addInitScript(([pid, image, file]) => {
    window.localStorage.setItem(`undm.stage.${pid}`, JSON.stringify({ bbu: { firstLogin: false, imageId: image, allowDowngrade: false,
      alsoSecondary: false, baseId: null, siteId: null, fileId: file, loginAfter: null, secrets: {} } }));
  }, [p.id, img.id, scf.id]);

  await page.goto(`/stage/${p.id}?step=3`);
  const card = page.locator('.mantine-Card-root', { hasText: name });
  await card.getByRole('button', { name: 'Check now' }).click();
  await expect(card.getByText(`SBTS_E2E_${id}.zip · SBTS-E2E-${id}`)).toBeVisible();
  await card.getByLabel('Where in the portal, and the version it shows now').fill('Software page; shows the new version');
  await card.getByRole('button', { name: 'Done' }).click();
  await expect(card.getByText(`scf_e2e_${id}.xml`)).toBeVisible();
  await card.getByLabel('Where in the portal, and what it reported').fill('Commissioning; activated');
  await card.getByRole('button', { name: 'Done' }).click();
  await card.getByLabel('What the portal shows').fill('On air, no alarms');
  await card.getByRole('button', { name: 'Done' }).click();
  await expect(card.getByText('Staged', { exact: true })).toBeVisible();

  await page.goto(`/stage/${p.id}?step=4`);
  await expect(page.getByRole('table', { name: `Steps done in the portal of ${name}` })).toContainText('On air, no alarms');
});

/** What a simulated BBU offers (D-130): the ports read without a login, then the NETCONF <hello> with
 *  a login a person chooses. SYNTHETIC answers; nothing is contacted. */
test('the Flexi BBU tells which management services it offers', async ({ page, request }) => {
  const id = String(Date.now()).slice(-6);
  const p = await (await request.post('/api/projects', { data: { name: `E2E bbu services ${id}`, purpose: 'Staging' } })).json();
  const ref = await (await request.post(`/api/projects/${p.id}/credential-refs`,
    { data: { name: `bbu-${id}`, provider: 'env', locator: 'e2e-modem' } })).json();
  test.skip(!ref.has_secret, 'the backend has no UNDM_CRED_E2E_MODEM_USERNAME / _PASSWORD');
  const name = `e2e-${id}-bbu`;
  const bbu = await (await request.post(`/api/projects/${p.id}/devices`, { data: {
    name, manufacturer: 'Nokia', model: 'FSMF', category: 'other', driver_id: 'mock.nokia.flexi', environment: 'simulated',
    management_address: '192.0.2.129' } })).json();

  await page.goto(`/devices/${bbu.id}`);
  await page.getByRole('button', { name: `Actions for ${name}` }).click();
  await page.getByText('Find its management services…').click();
  const dialog = page.getByRole('dialog', { name: `Management services · ${name}` });
  await dialog.getByRole('button', { name: 'Read its services' }).click();
  const ports = dialog.getByRole('table', { name: 'Management ports' });
  await expect(ports).toContainText('SSH-2.0-SIMULATED');
  await expect(dialog.getByText('Simulated: nothing was sent').first()).toBeVisible();
  await dialog.getByRole('combobox', { name: 'Login to read it with' }).click();
  await page.getByRole('option', { name: new RegExp(`bbu-${id}`) }).click();
  await dialog.getByRole('button', { name: 'Read its NETCONF capabilities' }).click();
  await expect(dialog.getByRole('table', { name: 'YANG modules it announces' })).toContainText('simulated-software');
});

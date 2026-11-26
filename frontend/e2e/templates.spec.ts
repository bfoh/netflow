import { expect, test } from '@playwright/test';

/** Team templates (D-111): a synthetic template, a system with a zone in its name, Generate in
 *  the wizard. Fictional zone 41/7, RFC 1918 / 5737 addresses; nothing contacted. */
test('generate a device file from a template for the system zone', async ({ page, request }) => {
  const id = String(Date.now()).slice(-5);
  // Written as many team files are: Windows line endings, no line break after the last line.
  const lines = ['hostname "z041e2esw01"', 'ip route 0.0.0.0 0.0.0.0 10.168.248.254', 'vlan 222', '   untagged 2',
    '   ip address 192.168.1.1 255.255.255.0', '   exit'];
  const text = lines.join('\r\n');
  const tpl = await request.post('/api/templates', { data: { role: 'bhdmz', filename: `z041-E2eSw-v${id}.pcc`, text } });
  expect(tpl.status()).toBe(201);
  const p = await (await request.post('/api/projects', { data: { name: `E2E z007 ${id}`, purpose: 'Staging' } })).json();
  await request.post(`/api/projects/${p.id}/devices`, { data: {
    name: `e2e-a-${id}`, manufacturer: 'Aruba', model: '2930F', category: 'switch', os_family: 'ArubaOS-Switch',
    driver_id: 'mock.aruba.aos_switch', environment: 'simulated', management_address: '192.168.1.1', role: 'Aruba 2930F (OOBM port 2)' } });

  await page.goto(`/stage/${p.id}?step=0`);
  await expect(page.getByLabel('Zone')).toHaveValue('7');
  // D-121: saved by itself.
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  await page.goto(`/stage/${p.id}?step=1`);
  await page.getByRole('button', { name: 'Generate the files for zone 7' }).click();
  await expect(page.getByText(/files? made for zone 7/)).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Team file' })).toHaveValue(new RegExp(`z007-E2eSw-v${id}\\.pcc`));
  await page.getByRole('button', { name: "Compare with the devices' files" }).click();
  await expect(page.getByText('no file on the device to compare')).toBeVisible();
  // The download is byte for byte as the team writes the file.
  const [download] = await Promise.all([page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download the files for zone 7' }).click()]);
  expect(download.suggestedFilename()).toMatch(/^E2E_z007_\d+-files\.zip$/);
  const one = await request.get('/api/templates/bhdmz/file?zone=7');
  expect((await one.body()).toString('utf8')).toBe(text.replace('z041', 'z007').replace('10.168.', '10.134.'));
});

import { expect, test } from '@playwright/test';

/** After staging (D-125): a practice system is moved to the network through its BFW, its
 *  simulated devices answer at their network addresses, then it goes back to the bench.
 *  Simulated devices only; fictional names and RFC 5737 addresses. */
test('a practice system is reached in the network through its BFW, then back on the bench', async ({ page, request }) => {
  const tag = Math.random().toString(36).slice(2, 8);
  const json = async (r: Awaited<ReturnType<typeof request.post>>) => {
    if (!r.ok()) throw new Error(`${r.url()} → ${r.status()} ${await r.text()}`);
    return r.json();
  };
  const project = await json(await request.post('/api/projects', { data: { name: `Practice B009 ${tag}` } }));
  const add = (body: Record<string, unknown>) => request.post(`/api/projects/${project.id}/devices`, { data: { environment: 'simulated', ...body } });
  const fw = await json(await add({ name: `abc-fw-${tag}`, manufacturer: 'Fortinet', model: 'FortiGate-101F', category: 'firewall',
    driver_id: 'mock.fortinet.fortios', management_address: '192.168.1.99' }));
  const sw = await json(await add({ name: `abc-sw-${tag}`, manufacturer: 'Aruba', model: '2930F', category: 'switch',
    driver_id: 'mock.aruba.aos_switch', management_address: '192.168.1.1' }));
  await json(await request.post(`/api/devices/${sw.id}/configs/import`, { data: { filename: `abc-sw-${tag}.pcc`, text:
    '; JL260A Configuration Editor; Created on release #WC.16.10.0025\nhostname "abc-sw"\nvlan 222\n   name "OOBM"\n'
    + '   untagged 2\n   ip address 192.168.1.1 255.255.255.0\n   exit\nvlan 310\n   tagged 49\n'
    + '   ip address 198.51.100.11 255.255.255.0\n   exit\n' } }));
  await json(await request.put(`/api/devices/${fw.id}/network-address`, { data: { address: '198.51.100.1' } }));

  await page.goto(`/systems/${project.id}?tab=network`);
  await expect(page.getByRole('heading', { name: 'Where UNDM reaches this system' })).toBeVisible();
  // The switch's network address, chosen from its file.
  await page.getByRole('button', { name: `Choose the network address of abc-sw-${tag} from its file` }).click();
  const chooser = page.getByRole('dialog');
  await expect(chooser.getByText('suggested', { exact: true })).toBeVisible();
  await chooser.getByRole('button', { name: 'Use 198.51.100.11' }).click();
  await expect(chooser).toBeHidden();

  await page.getByRole('button', { name: 'Move to the network…' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Move to the network' }).click();
  await expect(page.getByRole('button', { name: 'Move back to the bench…' })).toBeVisible();
  const table = page.getByRole('table', { name: 'Devices of this system in the network' });
  await expect(table.getByRole('row', { name: new RegExp(`abc-sw-${tag}`) }).getByText('198.51.100.11').first()).toBeVisible();

  // UNDM's own test reaches the simulated unit at its network address.
  const test1 = await json(await request.post(`/api/devices/${sw.id}/operations/check_reachability`));
  expect(test1.status).toBe('success');
  // Plans stay on the bench.
  const refused = await request.post(`/api/devices/${sw.id}/restart-plan`);
  expect(refused.status()).toBe(409);

  await page.getByRole('button', { name: 'Move back to the bench…' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Move back to the bench' }).click();
  await expect(page.getByRole('button', { name: 'Move to the network…' })).toBeVisible();
  const back = await json(await request.get(`/api/devices/${sw.id}`));
  expect(back.connection.address).toBe('192.168.1.1');
});

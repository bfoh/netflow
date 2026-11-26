import type { APIRequestContext } from '@playwright/test';

/** A fictional system for page checks (D-119): simulated devices only, RFC 5737 addresses,
 *  made-up names. Returns the ids the checks open. */
export async function seedSystem(request: APIRequestContext, tag = Math.random().toString(36).slice(2, 8)) {
  const json = async (r: Awaited<ReturnType<APIRequestContext['post']>>) => {
    if (!r.ok()) throw new Error(`${r.url()} → ${r.status()} ${await r.text()}`);
    return r.json();
  };
  const project = await json(await request.post('/api/projects', { data: { name: `Practice B007z041 ${tag}`, purpose: 'Staging' } }));
  const device = (name: string, body: Record<string, unknown>) => request.post(`/api/projects/${project.id}/devices`, {
    data: { name: `${name}-${tag}`, environment: 'simulated', ...body } });
  const sw = await json(await device('lab-bb', { manufacturer: 'Black Box', model: 'LIG1014A', category: 'switch',
    os_family: 'Black Box managed switch', driver_id: 'mock.blackbox.switch', management_address: '192.0.2.1',
    role: 'Black Box LIG1014A' }));
  await json(await device('lab-fw', { manufacturer: 'Fortinet', model: 'FortiGate-101F', category: 'firewall',
    os_family: 'FortiOS', driver_id: 'mock.fortinet.fortios', management_address: '192.0.2.99', role: 'FortiGate 101F' }));
  // A finished staging plan on the switch, made the way the wizard makes it, so plan pages have content.
  const version = await json(await request.post(`/api/devices/${sw.id}/configs/import`, { data: {
    filename: `team-${tag}.txt`, text: `hostname e2e-bb-${tag}\n!\nvlan 1001\n!\ninterface GigabitEthernet 1/3\n description Port-3\n!\n`
      + 'interface vlan 1\n ip address 192.0.2.1 255.255.255.0\n!\nend\n' } }));
  const staging = await json(await request.post(`/api/projects/${project.id}/device-staging`, { data: {
    device_id: sw.id, steps: [{ kind: 'configuration', version_id: version.id }] } }));
  await request.post(`/api/staging-plans/${staging.staging_id}/approve`);
  await request.post(`/api/staging-plans/${staging.staging_id}/execute?background=false`);
  const plan = { id: staging.steps[0].id as string };
  return { projectId: project.id as string, deviceId: sw.id as string, planId: plan.id as string };
}

import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Device, DeviceServices } from '../src/types/api';
import { mockApi, renderAt } from './render';

const device = (over: Partial<Device>): Device => ({
  id: 'd1', project_id: 'p1', name: 'sw1', manufacturer: 'Aruba', product_family: '', model: '2930F',
  hardware_revision: '', category: 'switch', role: '', os_family: 'ArubaOS-Switch', firmware_version: '',
  management_address: '192.0.2.10', management_protocol: 'ssh', management_port: null, management_vrf: '',
  site: '', rack_location: '', driver_id: 'ssh.aruba.aos_switch', credential_ref_id: 'c1', environment: 'lab',
  provisioning_status: 'planned', deployment_status: 'never_deployed', notes: '', tags: [], intent: null,
  observed_facts: null, facts_retrieved_at: null, last_connection_at: null, last_backup_at: null,
  last_deployment_at: null, locked_by_deployment_id: null, bootstrap_profile: null,
  capabilities: ['supports_restart', 'supports_ssh'], created_at: '', updated_at: '',
  ...over,
});
const project = { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '', certificate_subject: null };
const fw = device({ id: 'fw', name: 'lab-fw', category: 'firewall', model: 'FortiGate-101F', driver_id: 'ssh.fortinet.fortios',
  capabilities: ['supports_ssh'], management_address: '192.168.1.99' });
const sw = device({ id: 'sw', name: 'lab-sw-a' });
const sim = device({ id: 'sim', name: 'lab-bb', environment: 'simulated', driver_id: 'mock.blackbox.switch', capabilities: [] });

describe('device menu, tree and watch (D-099)', () => {
  it('the system tree groups devices by kind and shares its tick boxes with the table', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [fw, sw, sim] });
    renderAt('/systems/p1');
    // D-122: the tree is shown beside the table on request, remembered.
    await userEvent.click(await screen.findByRole('radio', { name: 'Table and tree' }));
    expect(window.localStorage.getItem('undm.system.view')).toBe('tree');
    const tree = await screen.findByLabelText('Devices of Lab A');
    expect(within(tree).getByText('Firewalls')).toBeInTheDocument();
    expect(within(tree).getByText('Switches')).toBeInTheDocument();
    await userEvent.click(within(tree).getByRole('checkbox', { name: 'Select all switches' }));
    expect(screen.getByText(/Selected:/).textContent).toContain('2');  // lab-sw-a and lab-bb
  });

  it('right-click opens the menu with what applies to that device', async () => {
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [fw, sw, sim] });
    renderAt('/systems/p1');
    const row = (await screen.findAllByRole('link', { name: 'lab-fw' })).at(-1)!.closest('tr')!;
    fireEvent.contextMenu(row);
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByText('Open SSH window')).toBeInTheDocument();
    expect(within(menu).getByText('Open web page').closest('a')).toHaveAttribute('href', 'https://192.168.1.99');
    expect(within(menu).getByText('Read information')).toBeInTheDocument();
    expect(within(menu).queryByText('Restart…')).not.toBeInTheDocument();  // no verified restart for it
  });

  it('a simulated device offers no SSH window', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [sim] });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for lab-bb' }));
    expect(await screen.findByText('Read information')).toBeInTheDocument();  // the menu is open
    expect(screen.queryByText('Open SSH window')).not.toBeInTheDocument();
  });

  it('the modem (console only) opens a console window instead of SSH (D-118)', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const modem = device({ id: 'm1', name: 'lab-modem', category: 'router', model: '7705 SAR-Hmc', driver_id: 'console.nokia.sar',
      management_address: '', console_port: 'COM7', capabilities: ['supports_serial_console', 'supports_configuration_apply'] });
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [modem],
      '/devices/m1/console-settings': { console_port: 'COM7', console_speed: 115200, source: "Nokia's documentation, used on the bench", speeds: [] },
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: '', hardware_id: '' }, { port: 'COM7', description: 'USB Serial Port', hardware_id: '' }],
      '/devices/m1/open-console': { program: 'putty', console_port: 'COM7', console_speed: 115200, command: 'putty -serial COM7' } });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for lab-modem' }));
    expect(await screen.findByText('Open console window…')).toBeInTheDocument();
    expect(screen.queryByText('Open SSH window')).not.toBeInTheDocument();
    expect(screen.queryByText('Wait until it answers')).not.toBeInTheDocument();  // no network address
    await userEvent.click(screen.getByText('Open console window…'));
    const dialog = await screen.findByRole('dialog', { name: 'Console window · lab-modem' });
    expect(await within(dialog).findByText(/115200: Nokia's documentation/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Open console window' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/m1/open-console' && c.init?.method === 'POST')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/devices/m1/open-console');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ console_port: 'COM7', console_speed: null });  // its own speed: not saved
  });

  it('every real device has a console window, a 2930F included (D-126)', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [sw],
      '/devices/sw/console-settings': { console_port: null, console_speed: 9600, source: "the team's setting, used on the bench", speeds: [] },
      '/provisioning/serial-ports': [{ port: 'COM4', description: 'USB Serial Port', hardware_id: '' }],
      '/devices/sw/open-console': { program: 'miniterm', console_port: 'COM4', console_speed: 9600, command: '' } });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for lab-sw-a' }));
    await userEvent.click(await screen.findByText('Open console window…'));
    const dialog = await screen.findByRole('dialog', { name: 'Console window · lab-sw-a' });
    const open = within(dialog).getByRole('button', { name: 'Open console window' });
    expect(open).toBeDisabled();  // no port chosen yet
    await userEvent.click(within(dialog).getByLabelText('COM port of this PC'));
    await userEvent.click(await screen.findByRole('option', { name: /COM4/, hidden: true }));
    await userEvent.click(open);
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/sw/open-console')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/devices/sw/open-console');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ console_port: 'COM4', console_speed: null });
  });

  it('a 2930F offers restart and console setup', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [sw] });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for lab-sw-a' }));
    expect(await screen.findByText('Restart…')).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Console setup', hidden: true })).toBeInTheDocument();  // also a sidebar link
  });

  it('a restart is made as a plan and opens the plan page', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [sw],
      '/devices/sw/restart-plan': { id: 'dep9', kind: 'restart', state: 'awaiting_approval', events: [], targets: [] } });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(within(table).getByRole('button', { name: 'Actions for lab-sw-a' }));
    await userEvent.click(await screen.findByText('Restart…'));
    const dialog = await screen.findByRole('dialog', { name: 'Restart lab-sw-a' });
    expect(within(dialog).getByText(/not saved on the device are lost/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Make the restart plan' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/sw/restart-plan' && c.init?.method === 'POST')).toBe(true));
  });

  it('watching devices shows a dot per device from the reachability check', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [sw, sim],
      '/projects/p1/reachability': [{ device_id: 'sw', address: '192.0.2.10', state: 'no_answer' },
        { device_id: 'sim', address: '192.0.2.1', state: 'simulated' }] });
    window.localStorage.removeItem('undm.watch.p1');
    window.localStorage.setItem('undm.system.view', 'tree');
    renderAt('/systems/p1');
    await userEvent.click(await screen.findByRole('switch', { name: /Watch devices/ }));
    expect((await screen.findAllByRole('img', { name: 'No answer on its management port' })).length).toBe(2);  // tree and table
    expect(calls.some((c) => c.url === '/api/projects/p1/reachability')).toBe(true);
    window.localStorage.removeItem('undm.watch.p1');
    window.localStorage.removeItem('undm.system.view');
  });

  it('the device log lists entries and filters them', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/devices/sw': sw, '/projects/p1': project, '/devices/sw/log': [
      { time: '2026-11-25T10:00:00Z', source: 'plan', kind: 'restart.deploy', status: 'ok', message: 'restarting', actor: '', plan_id: 'dep9' },
      { time: '2026-11-25T09:00:00Z', source: 'audit', kind: 'provisioning.console_bootstrap', status: 'bootstrapped', message: 'saved', actor: 'x', plan_id: null },
    ] });
    renderAt('/devices/sw?tab=log');
    expect(await screen.findByText('restarting')).toBeInTheDocument();
    expect(screen.getByText('saved')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Console'));
    expect(screen.queryByText('restarting')).not.toBeInTheDocument();
    expect(screen.getByText('saved')).toBeInTheDocument();
  });

  it('a FortiGate offers Load license…: the file is uploaded and a plan is made', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const fortigate = device({ id: 'fw', name: 'lab-fw', category: 'firewall', model: 'FortiGate-101F',
      driver_id: 'ssh.fortinet.fortios', capabilities: ['supports_ssh', 'supports_license_file'] });
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [fortigate],
      '/devices/fw/license': { id: 'lic1', filename: 'lab-fw.lic', sha256: 'x' },
      '/devices/fw/license-plan': { id: 'dep7', kind: 'license', state: 'awaiting_approval', events: [], targets: [] } });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for lab-fw' }));
    await userEvent.click(await screen.findByText('Load license…'));
    const dialog = await screen.findByRole('dialog', { name: 'Load a license on lab-fw' });
    const input = dialog.querySelector('input[type=file]') as HTMLInputElement;
    await userEvent.upload(input, new File(['SYNTHETIC'], 'lab-fw.lic'));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Make the license plan' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/fw/license-plan')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/devices/fw/license-plan');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ version_id: 'lic1' });
    expect(calls.find((c) => c.url === '/api/devices/fw/license')?.init?.body).toBeInstanceOf(FormData);
  });
});

describe('management services of the Flexi BBU (D-130)', () => {
  const bbu = device({ id: 'b1', name: 'lab-bbu', manufacturer: 'Nokia', category: 'other', model: 'FSMF',
    driver_id: 'guided.nokia.flexi', management_address: '192.168.255.1', credential_ref_id: null,
    capabilities: ['supports_guided_staging', 'supports_service_discovery'] });
  const reading: DeviceServices = {
    services: { address: '192.168.255.1', simulated: false, at: '2026-11-27T10:00:00Z', message: '2 of 3 management ports answer',
      ports: [
        { port: 22, kind: 'ssh', name: 'SSH', reference: 'RFC 4253', open: false, banner: null, certificate: null, note: 'No connection (closed, filtered or nothing listening).' },
        { port: 443, kind: 'https', name: 'HTTPS (web portal)', reference: 'RFC 8446', open: true, banner: null,
          certificate: { subject: 'CN=abc-bbu.example', issuer: 'CN=abc-ca.example', not_after: '2030-01-01T00:00:00+00:00', sha256: '0'.repeat(64) }, note: '' },
        { port: 830, kind: 'netconf', name: 'NETCONF over SSH', reference: 'RFC 6242', open: true, banner: 'SSH-2.0-AbcSSH', certificate: null, note: '' },
      ] },
  };

  it('the menu reads what each port presents, and NETCONF waits for a login', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [bbu], '/devices/b1/services': reading,
      '/devices/b1/services/discover': reading.services,
      '/projects/p1/credential-refs': [{ id: 'c9', name: 'bbu-login', provider: 'keyring', locator: 'x', has_secret: true, project_id: 'p1' }] });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for lab-bbu' }));
    await userEvent.click(await screen.findByText('Find its management services…'));
    const dialog = await screen.findByRole('dialog', { name: 'Management services · lab-bbu' });
    const ports = await within(dialog).findByRole('table', { name: 'Management ports' });
    expect(within(ports).getByText('SSH-2.0-AbcSSH')).toBeInTheDocument();
    expect(within(ports).getByText('Certificate: CN=abc-bbu.example')).toBeInTheDocument();
    const read = within(dialog).getByRole('button', { name: 'Read its NETCONF capabilities' });
    expect(read).toBeDisabled();
    expect(within(dialog).getByText('Choose a login first.')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Read them again' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/b1/services/discover' && c.init?.method === 'POST')).toBe(true));
    expect(calls.some((c) => c.url.includes('netconf-hello'))).toBe(false);  // nothing logs in without a person's choice
  });

  it('the copied result lists the ports and the announced capabilities, never a secret', async () => {
    const { asText } = await import('../src/features/devices/servicesText');
    const text = asText(bbu, { ...reading, netconf_hello: { ok: true, at: '2026-11-27T10:01:00Z', login: 'bbu-login',
      message: 'It announces 2 capabilities and 1 YANG modules', base_versions: ['1.0'], session_id: '7', host_key: 'ssh-rsa SHA256:abc',
      capabilities: ['urn:ietf:params:netconf:base:1.0', 'urn:example:abc:sw?module=abc-software&revision=2026-01-01'] } });
    expect(text).toContain('830 NETCONF over SSH: answers | SSH-2.0-AbcSSH');
    expect(text).toContain('22 SSH: no answer');
    expect(text).toContain('urn:example:abc:sw?module=abc-software');
    expect(text).toContain('login "bbu-login"');
    const { unitMasked } = await import('../src/features/devices/servicesText');
    expect(unitMasked('CN=AB1234567.example.com,O=Example')).toBe('CN=<unit>.example.com,O=Example');
  });
});

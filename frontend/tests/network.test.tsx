import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Device, FileAddresses, Project } from '../src/types/api';
import { mockApi, renderAt } from './render';

const device = (over: Partial<Device>): Device => ({
  id: 'd1', project_id: 'p1', name: 'sw1', manufacturer: 'Aruba', product_family: '', model: '2930F',
  hardware_revision: '', category: 'switch', role: '', os_family: 'ArubaOS-Switch', firmware_version: '',
  management_address: '192.168.1.1', management_protocol: 'ssh', management_port: null, management_vrf: '',
  site: '', rack_location: '', driver_id: 'ssh.aruba.aos_switch', credential_ref_id: 'c1', environment: 'lab',
  provisioning_status: 'planned', deployment_status: 'never_deployed', notes: '', tags: [], intent: null,
  observed_facts: null, facts_retrieved_at: null, last_connection_at: null, last_backup_at: null,
  last_deployment_at: null, locked_by_deployment_id: null, bootstrap_profile: null,
  capabilities: ['supports_restart', 'supports_ssh'], created_at: '', updated_at: '',
  ...over,
});
const project = (over: Partial<Project> = {}): Project => ({
  id: 'p1', name: 'Practice B007', description: '', site: '', purpose: '', created_at: '', updated_at: '',
  reached_via: 'bench', network_gateway_id: null, ...over,
});
const fw = device({ id: 'fw', name: 'abc-fw', category: 'firewall', model: 'FortiGate-101F', driver_id: 'ssh.fortinet.fortios',
  management_address: '192.168.1.99', network_address: '198.51.100.1', capabilities: ['supports_ssh'] });
const sw = device({ id: 'sw', name: 'abc-sw-a' });
const swFile: FileAddresses = {
  files: [{ version_id: 'v1', name: 'abc-sw-a.pcc', loaded: true, created_at: '' }], reader: true,
  addresses: [
    { address: '192.168.1.1', prefix: 24, where: 'VLAN 222', line: 11, vdom: null, allows: '', file: 'abc-sw-a.pcc', version_id: 'v1', on_bench: true },
    { address: '198.51.100.11', prefix: 24, where: 'VLAN 310', line: 16, vdom: null, allows: '', file: 'abc-sw-a.pcc', version_id: 'v1', on_bench: false },
  ],
  managers: [{ first: '198.51.100.0', last: '198.51.100.255', text: '198.51.100.0/24 (manager)', line: 19, file: 'abc-sw-a.pcc' }],
  suggested: '198.51.100.11', reason: 'The only address its files give it outside the bench.',
  pc_address: '198.51.100.50', pc_allowed: true, route_hint: null,
};
const policy = { enable_real_device_writes: false, enable_real_device_firmware: false, allow_production_read_only: false,
  allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: true, locked: [] };

describe('after staging: the system in the network (D-125)', () => {
  it('moving to the network says the devices become production and sends the BFW', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project(), '/projects/p1/devices': [fw, sw], '/policy': policy,
      '/devices/sw/file-addresses': swFile, '/projects/p1/reached-via': project({ reached_via: 'network' }) });
    renderAt('/systems/p1?tab=network');
    expect(await screen.findByText('Where UNDM reaches this system')).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Devices of this system in the network' });
    expect(within(table).getByText('198.51.100.1')).toBeInTheDocument();
    expect(within(table).getByText('BFW')).toBeInTheDocument();  // its only firewall
    await userEvent.click(screen.getByRole('button', { name: 'Move to the network…' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/become/).textContent).toContain('production');
    expect(within(dialog).getByText(/Still without a network address: abc-sw-a/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Move to the network' }));
    const put = calls.find((c) => c.url.endsWith('/projects/p1/reached-via'));
    expect(put?.init?.method).toBe('PUT');
    expect(JSON.parse(String(put?.init?.body))).toEqual({ via: 'network', gateway_device_id: 'fw' });
  });

  it('the network address is chosen from its file, with the file and line kept', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project(), '/projects/p1/devices': [fw, sw], '/policy': policy,
      '/devices/sw/file-addresses': swFile, '/devices/sw/network-address': { ...sw, network_address: '198.51.100.11' } });
    renderAt('/systems/p1?tab=network');
    await userEvent.click(await screen.findByRole('button', { name: 'Choose the network address of abc-sw-a from its file' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('suggested')).toBeInTheDocument();
    expect(within(dialog).getByText('abc-sw-a.pcc, line 16')).toBeInTheDocument();
    expect(within(dialog).getByText(/This PC's address towards it now/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Use 198.51.100.11' }));
    const put = calls.find((c) => c.url.endsWith('/devices/sw/network-address'));
    expect(JSON.parse(String(put?.init?.body))).toEqual({ address: '198.51.100.11', file: 'abc-sw-a.pcc', line: 16 });
  });

  it('in the network, the start-up setting for UNDM’s own logins is shown to copy', async () => {
    mockApi({ '/projects/p1': project({ reached_via: 'network', network_gateway_id: 'fw' }),
      '/projects/p1/devices': [{ ...fw, environment: 'production' }], '/policy': policy });
    renderAt('/systems/p1?tab=network');
    expect(await screen.findByText("UNDM's own logins to these devices are off")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move back to the bench…' })).toBeInTheDocument();
  });

  it('in the network, the device menu keeps changes for the bench', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const inNet = { ...sw, environment: 'production' as const, network_address: '198.51.100.11',
      connection: { via: 'network' as const, address: '198.51.100.11', port: null, driver_id: sw.driver_id, capabilities: sw.capabilities, problem: null } };
    mockApi({ '/projects/p1': project({ reached_via: 'network' }), '/projects/p1/devices': [inNet] });
    renderAt('/systems/p1');
    const table = await screen.findByRole('table');
    await userEvent.click(await within(table).findByRole('button', { name: 'Actions for abc-sw-a' }));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByText('In the network: 198.51.100.11')).toBeInTheDocument();
    expect(within(menu).getByText('Open web page').closest('a')).toHaveAttribute('href', 'https://198.51.100.11');
    expect(within(menu).getByText('Restart…').closest('button')).toBeDisabled();
    expect(within(menu).getByText('Make a plan…').closest('button')).toBeDisabled();
  });
});

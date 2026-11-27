import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Device, TraceAnswer } from '../src/types/api';
import { mockApi, renderAt } from './render';

const device = (over: Partial<Device>): Device => ({
  id: 'd1', project_id: 'p1', name: 'sw1', manufacturer: 'Aruba', product_family: '', model: '2930F',
  hardware_revision: '', category: 'switch', role: '', os_family: 'ArubaOS-Switch', firmware_version: '',
  management_address: '192.168.1.1', management_protocol: 'ssh', management_port: null, management_vrf: '',
  site: '', rack_location: '', driver_id: 'mock.aruba.aos_switch', credential_ref_id: null, environment: 'simulated',
  provisioning_status: 'planned', deployment_status: 'never_deployed', notes: '', tags: [], intent: null,
  observed_facts: null, facts_retrieved_at: null, last_connection_at: null, last_backup_at: null,
  last_deployment_at: null, locked_by_deployment_id: null, bootstrap_profile: null,
  capabilities: [], created_at: '', updated_at: '', ...over,
});
const fw = device({ id: 'fw', name: 'abc-fw', category: 'firewall', management_address: '192.168.1.99' });
const a = device({ id: 'a', name: 'abc-sw-a' });
const b = device({ id: 'b', name: 'abc-sw-b' });
const project = { id: 'p1', name: 'Practice B007', description: '', site: '', purpose: '', created_at: '', updated_at: '' };
const trace: TraceAnswer = {
  source: 'pc', target: '192.168.1.1', reached: true, simulated: false, note: '', target_device: null,
  raw: 'Tracing route to 192.168.1.1', hops: [
    { n: 1, address: '192.168.1.99', rtt_ms: [1, 1, null], timed_out: false, device_id: 'fw', interface: 'bench address', candidates: [] },
    { n: 2, address: null, rtt_ms: [null, null, null], timed_out: true, device_id: null, interface: null, candidates: [] },
    { n: 3, address: '192.168.1.1', rtt_ms: [2, 2, 2], timed_out: false, device_id: null, interface: null, candidates: ['a', 'b'] },
  ] };

describe('troubleshooting (D-128)', () => {
  it('the hop table names a hop device, and candidates when two share an address', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/devices/a': a, '/projects/p1': project, '/projects/p1/devices': [fw, a, b],
      '/projects/p1/troubleshoot/traceroute': trace });
    renderAt('/devices/a?tab=troubleshoot');
    expect(await screen.findByRole('heading', { name: 'Ping and traceroute' })).toBeInTheDocument();
    expect(screen.getByLabelText('To')).toHaveValue('192.168.1.1');  // its own address in use
    await userEvent.click(screen.getByRole('button', { name: 'Traceroute' }));
    const table = await screen.findByRole('table', { name: 'Hops to 192.168.1.1' });
    expect(within(table).getByRole('link', { name: 'abc-fw' })).toBeInTheDocument();
    expect(within(table).getByText('no answer')).toBeInTheDocument();
    expect(within(table).getByText('one of abc-sw-a, abc-sw-b')).toBeInTheDocument();
    expect(within(table).getByText('1 ms · 1 ms · *')).toBeInTheDocument();
    const sent = calls.find((c) => c.url.endsWith('/troubleshoot/traceroute'));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ source: 'pc', target: '192.168.1.1' });
  });

  it('a simulated ping says nothing was sent, and a typed range is not accepted', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/devices/a': a, '/projects/p1': project, '/projects/p1/devices': [fw, a],
      '/projects/p1/troubleshoot/ping': { source: 'pc', target: '192.168.1.99', sent: 4, received: 4, rtt_ms: [1, 1, 1, 1],
        simulated: true, raw: '', note: 'Simulated: nothing was sent.', answered: true, target_device: 'fw' } });
    renderAt('/devices/a?tab=troubleshoot');
    await userEvent.click(await screen.findByRole('button', { name: 'abc-fw · 192.168.1.99' }));
    await userEvent.click(screen.getByRole('button', { name: 'Ping' }));
    expect(await screen.findByText('Simulated: nothing was sent.')).toBeInTheDocument();
    expect(screen.getByText(/4 of 4 replies/)).toBeInTheDocument();
    const to = screen.getByLabelText('To');
    await userEvent.clear(to);
    await userEvent.type(to, '192.168.1.0/24');
    expect(screen.getByRole('button', { name: 'Ping' })).toBeDisabled();
  });
});

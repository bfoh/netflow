import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Device } from '../src/types/api';
import { mockApi, renderAt } from './render';

const device = (over: Partial<Device>): Device => ({
  id: 'd1', project_id: 'p1', name: 'sw1', manufacturer: 'Aruba', product_family: 'CX', model: '6300M',
  hardware_revision: '', category: 'switch', role: 'access', os_family: 'AOS-CX', firmware_version: '',
  management_address: '10.0.0.1', management_protocol: 'ssh', management_port: null, management_vrf: '',
  site: '', rack_location: '', driver_id: 'mock.aruba.aoscx', credential_ref_id: null, environment: 'simulated',
  provisioning_status: 'planned', deployment_status: 'never_deployed', notes: '', tags: [], intent: null,
  observed_facts: null, facts_retrieved_at: null, last_connection_at: null, last_backup_at: null,
  last_deployment_at: null, locked_by_deployment_id: null, bootstrap_profile: null, capabilities: [], created_at: '', updated_at: '',
  ...over,
});

describe('application shell', () => {
  it('shows every module in the main navigation', async () => {
    mockApi({});
    renderAt('/');
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    for (const label of ['Dashboard', 'Projects', 'Network Elements', 'Topology', 'Configurations',
      'Provisioning', 'Firmware', 'Deployments', 'Logs & Audit', 'Settings']) {
      expect(within(nav).getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('Real-device changes off')).toBeInTheDocument();
  });

  it('dashboard summarises inventory and deployments', async () => {
    mockApi({
      '/devices': [device({}), device({ id: 'd2', name: 'fw1', manufacturer: 'Fortinet', category: 'firewall', last_connection_at: '2026-01-01T00:00:00Z' })],
      '/projects': [{ id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '' }],
      '/deployments': [{ id: 'x', project_id: 'p1', state: 'awaiting_approval', dry_run: false, apply_mode: 'merge', created_by: 'a', approved_by: null, created_at: '2026-01-01T00:00:00Z' }],
    });
    renderAt('/');
    expect(await screen.findByText('Fortinet')).toBeInTheDocument();
    const pending = screen.getByText('Pending approvals').parentElement!;
    expect(within(pending).getByText('1')).toBeInTheDocument();
    expect(screen.getByText('awaiting approval')).toBeInTheDocument();
  });

  it('inventory marks simulated devices and offers only read-only bulk actions', async () => {
    mockApi({ '/devices': [device({})], '/projects': [] });
    renderAt('/devices');
    expect(await screen.findByText('sw1')).toBeInTheDocument();
    expect(screen.getByText('SIMULATED')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Perform' })).toBeDisabled();
  });

  it('provisioning page states what is not implemented yet', async () => {
    mockApi({});
    renderAt('/provisioning');
    expect(await screen.findByText(/Zero-touch and network-based provisioning is not implemented yet/)).toBeInTheDocument();
  });

  it('provisioning page previews the exact console commands for a switch', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'dmz-sw', driver_id: 'mock.aruba.aos_switch',
      bootstrap_profile: { vlan_id: 222, vlan_name: 'OOBM_VLAN', untagged_port: '2', address: '192.168.1.1/24' } });
    const calls = mockApi({
      '/devices': [sw, device({ id: 'cx', name: 'other', driver_id: 'mock.aruba.aoscx' })],
      '/drivers': [
        { driver_id: 'mock.aruba.aos_switch', platform: 'aos_switch', simulated: true, vendor: 'Aruba', os_family: 'ArubaOS-Switch', description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] },
        { driver_id: 'mock.aruba.aoscx', platform: 'aoscx', simulated: true, vendor: 'Aruba', os_family: 'AOS-CX', description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] },
      ],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated switch console', hardware_id: '' }, { port: 'COM7', description: 'USB Serial', hardware_id: '' }],
      '/devices/sw/provisioning/console-bootstrap/preview': { supported: true, commands: ['configure', 'vlan 222', 'untagged 2', 'write memory'], notes: ['Saved only after read-back.'] },
    });
    renderAt('/provisioning?device=sw');
    expect(await screen.findByDisplayValue('OOBM_VLAN')).toBeInTheDocument();
    expect(screen.getByDisplayValue('192.168.1.1/24')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Preview commands' }));
    expect(await screen.findByText(/untagged 2/)).toBeInTheDocument();
    const sent = calls.find((c) => c.url.endsWith('/console-bootstrap/preview'));
    expect(JSON.parse(String(sent?.init?.body)).profile.untagged_port).toBe('2');
    expect(screen.getByRole('button', { name: 'Run console bootstrap…' })).toBeEnabled();
  });

  it('header shows when real-device changes are enabled', async () => {
    mockApi({ '/policy': { enable_real_device_writes: true, allow_production_read_only: false,
      allow_production_deployments: false, require_separate_approver: false } });
    renderAt('/');
    expect(await screen.findByText('Real-device changes ON')).toBeInTheDocument();
  });

  it('firmware page lists images with integrity status', async () => {
    mockApi({ '/firmware/images': [{
      id: 'i1', vendor: 'Aruba', platform: 'aoscx', version: '10.1.0', filename: 'cx.swi', size_bytes: 2048,
      sha256: 'a'.repeat(64), vendor_sha256: 'a'.repeat(64), integrity_verified: true, compatible_models: ['6300M'],
      min_from_version: null, release_notes: '', status: 'uploaded', approved_by: null, approved_at: null,
      created_by: 'x', created_at: '2026-01-01T00:00:00Z' }] });
    renderAt('/firmware');
    expect(await screen.findByText('cx.swi')).toBeInTheDocument();
    expect(screen.getByText('verified')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled();
  });
});

describe('device page', () => {
  it('opens the intent editor when stored intent omits empty lists', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    // Shape written by the original demo seed: no "vlans" key on the firewall.
    const fw = device({ id: 'fw', name: 'branch-fw-01', manufacturer: 'Fortinet', category: 'firewall',
      intent: { hostname: 'branch-fw-01', interfaces: [{ interface: 'wan1', address: '198.51.100.2/30' }] } as never });
    mockApi({ '/devices/fw': fw });
    renderAt('/devices/fw');
    await userEvent.click(await screen.findByRole('tab', { name: 'Intent' }));
    expect(await screen.findByRole('button', { name: 'Add VLAN' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('wan1')).toBeInTheDocument();
  });

  it('shows the error page inside the app when a page crashes', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    // A device without the capabilities array makes the overview throw.
    mockApi({ '/devices/bad': { ...device({ id: 'bad' }), capabilities: undefined, tags: undefined } });
    renderAt('/devices/bad');
    expect(await screen.findByText('This page hit an error')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
  });
});


describe('observed facts', () => {
  it('shows extra facts as rows and raw output as readable blocks', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'lab-2930f', driver_id: 'ssh.aruba.aos_switch', environment: 'lab',
      observed_facts: { hostname: 'lab-2930f', model: '2930F-48G-4SFP', os_version: 'WC.16.10.0025',
        extra: { product_number: 'JL260A', rom_version: 'WC.16.01.0010',
          raw_output: { 'show modules': 'Chassis: 2930F-48G-4SFP  JL260A' } } } });
    mockApi({ '/devices/sw': sw });
    renderAt('/devices/sw');
    expect(await screen.findByText('JL260A')).toBeInTheDocument();
    expect(screen.getByText('WC.16.01.0010')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Raw command output (1)'));
    expect(await screen.findByText('show modules')).toBeInTheDocument();
    expect(screen.getByText(/Chassis: 2930F-48G-4SFP/)).toBeInTheDocument();
  });
});


describe('intent editor hostname safety', () => {
  it('defaults to the observed hostname and warns before renaming', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'inventory-name', observed_facts: { hostname: 'switch-real-name' } });
    mockApi({ '/devices/sw': sw });
    renderAt('/devices/sw');
    await userEvent.click(await screen.findByRole('tab', { name: 'Intent' }));
    const field = await screen.findByLabelText(/Hostname/);
    expect(field).toHaveValue('switch-real-name');
    expect(screen.queryByText('This intent renames the device')).not.toBeInTheDocument();
    await userEvent.clear(field);
    await userEvent.type(field, 'other');
    expect(screen.getByText('This intent renames the device')).toBeInTheDocument();
  });
});

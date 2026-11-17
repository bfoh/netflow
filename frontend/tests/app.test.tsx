import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Device } from '../src/types/api';
import { mockApi, renderAt } from './render';

const device = (over: Partial<Device>): Device => ({
  id: 'd1', project_id: 'p1', name: 'sw1', manufacturer: 'Aruba', product_family: 'CX', model: '6300M',
  hardware_revision: '', category: 'switch', role: 'access', os_family: 'AOS-CX', firmware_version: '',
  management_address: '10.0.0.1', management_protocol: 'ssh', management_port: null, management_vrf: '',
  site: '', rack_location: '', driver_id: 'mock.aruba.aoscx', credential_ref_id: null, environment: 'simulated',
  provisioning_status: 'planned', deployment_status: 'never_deployed', notes: '', tags: [], intent: null,
  observed_facts: null, facts_retrieved_at: null, last_connection_at: null, last_backup_at: null,
  last_deployment_at: null, locked_by_deployment_id: null, capabilities: [], created_at: '', updated_at: '',
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
    expect(screen.getByText('Simulation mode')).toBeInTheDocument();
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

  it('planned modules say they are not implemented', async () => {
    mockApi({});
    renderAt('/firmware');
    expect(await screen.findByText(/Firmware management is not implemented yet/)).toBeInTheDocument();
  });
});

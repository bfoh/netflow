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

  it('erasing a preconfigured switch needs its current login and hostname', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'dmz-sw', driver_id: 'mock.aruba.aos_switch',
      bootstrap_profile: { vlan_id: 222, vlan_name: 'OOBM_VLAN', untagged_port: '2', address: '192.168.1.1/24' } });
    const calls = mockApi({
      '/devices': [sw],
      '/drivers': [{ driver_id: 'mock.aruba.aos_switch', platform: 'aos_switch', simulated: true, vendor: 'Aruba', os_family: 'ArubaOS-Switch', description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated switch console', hardware_id: '' }],
      '/projects/p1/credential-refs': [{ id: 'old', name: 'preconfigured login' }],
      '/devices/sw/provisioning/console-bootstrap': { status: 'bootstrapped', message: 'ok', commands_sent: [], findings: [],
        verified: true, saved: true, transcript: '', sanitized_transcript: '', erased: 'lab-bhdmz-sw01',
        network_reachable: null, network_hint: '' },
    });
    renderAt('/provisioning?device=sw');
    await userEvent.click(await screen.findByRole('button', { name: 'Run console bootstrap…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Run console bootstrap' });
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /preconfigured/ }));
    await userEvent.type(within(dialog).getByLabelText(/Type the device name to confirm/), 'dmz-sw');
    const go = within(dialog).getByRole('button', { name: 'Erase and bootstrap' });
    expect(go).toBeDisabled();  // current login and hostname still missing
    await userEvent.click(within(dialog).getByPlaceholderText('Choose the preconfigured login'));
    await userEvent.click(await screen.findByRole('option', { name: 'preconfigured login', hidden: true }));
    await userEvent.type(within(dialog).getByLabelText(/Type its current hostname/), 'lab-bhdmz-sw01');
    expect(go).toBeEnabled();
    await userEvent.click(go);
    expect(await screen.findByText(/erased “lab-bhdmz-sw01” first/)).toBeInTheDocument();
    const sent = calls.find((c) => c.url.endsWith('/provisioning/console-bootstrap'));
    expect(JSON.parse(String(sent?.init?.body))).toMatchObject({ erase_existing: true,
      current_credential_ref_id: 'old', confirm_hostname: 'lab-bhdmz-sw01', allow_configured: false });
  });

  it('header shows when real-device changes are enabled', async () => {
    mockApi({ '/policy': { enable_real_device_writes: true, enable_real_device_firmware: false, allow_production_read_only: false,
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

describe('deployment outcome', () => {
  const plan = (over: Record<string, unknown>) => ({
    id: 'dep1', project_id: 'p1', kind: 'firmware', state: 'succeeded', dry_run: true, allow_downgrade: true, also_secondary: true,
    apply_mode: 'merge', created_by: 'tester', approved_by: null, created_at: '', firmware_image_id: 'i1',
    window_start: null, window_end: null, approved_at: null, updated_at: '',
    targets: [{ device_id: 'd1', position: 0, config_version_id: null, backup_version_id: null,
      from_version: 'WC.16.11.0001', to_version: 'WC.16.10.0025', state: 'preflight_passed', diff: '', message: '' }],
    events: [{ seq: 1, timestamp: '', device_id: null, stage: 'lifecycle', status: 'succeeded',
      message: 'dry run complete; no device was changed' }],
    ...over,
  });

  it('a successful dry run says nothing was changed and shows no deploy steps', async () => {
    mockApi({ '/deployments/dep1': plan({}), '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    expect(await screen.findByText('Dry run succeeded')).toBeInTheDocument();
    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument();
    expect(screen.queryByText(/Every upgraded device came back/)).not.toBeInTheDocument();
    expect(screen.queryByText('Deploy')).not.toBeInTheDocument();
    expect(screen.queryByText('Back up')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy events as text' })).toBeInTheDocument();
    expect(screen.getByText('Secondary flash too')).toBeInTheDocument();
  });

  it('a running deployment can be stopped after a confirmation', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/deployments/dep1': plan({ dry_run: false, state: 'deploying', approved_by: 'approver' }),
      '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    await userEvent.click(await screen.findByRole('button', { name: 'Stop' }));
    const dialog = await screen.findByRole('dialog', { name: 'Stop this deployment?' });
    expect(within(dialog).getByText(/no rollback is started/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith('/stop'))).toBe(false);  // nothing before confirming
    await userEvent.click(within(dialog).getByRole('button', { name: 'Stop' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/deployments/dep1/stop'
      && c.init?.method === 'POST')).toBe(true));
    expect(screen.queryByRole('button', { name: 'Execute deployment' })).not.toBeInTheDocument();
  });

  it('a restarting device is shown with a please-wait banner', async () => {
    mockApi({ '/deployments/dep1': plan({ dry_run: false, kind: 'configuration', state: 'deploying', approved_by: 'a',
      events: [{ seq: 9, timestamp: new Date().toISOString(), device_id: 'd1', stage: 'deploy', status: 'ok',
        message: 'waiting for the device to answer at 192.0.2.10 (up to 30 attempts, 20 s apart; Stop ends the wait)' }] }),
      '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    expect(await screen.findByText(/sw1 is restarting: please wait/)).toBeInTheDocument();
    expect(screen.getByText(/Do not power it off or unplug it/)).toBeInTheDocument();
    expect(screen.getByText(/Latest step/)).toBeInTheDocument();
  });

  it('shows the configuration read back after the deployment', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const target = { device_id: 'd1', position: 0, config_version_id: 'sent1', backup_version_id: 'b1',
      after_version_id: 'after1', from_version: null, to_version: null, state: 'verified', diff: '', message: '' };
    mockApi({ '/deployments/dep1': plan({ dry_run: false, kind: 'configuration', approved_by: 'a', targets: [target] }),
      '/projects/p1/devices': [device({})],
      '/configs/after1': { id: 'after1', text: 'hostname "lab-sw"\n', reference: 'after deployment dep1abcd' } });
    renderAt('/deployments/dep1');
    await userEvent.click(await screen.findByText('sw1'));
    await userEvent.click(await screen.findByRole('button', { name: 'View configuration after deployment' }));
    expect(await screen.findByText(/hostname "lab-sw"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare with what was sent' })).toBeInTheDocument();
  });

  it('a successful real upgrade keeps the upgrade wording', async () => {
    mockApi({ '/deployments/dep1': plan({ dry_run: false, approved_by: 'approver' }), '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    expect(await screen.findByText('Deployment succeeded')).toBeInTheDocument();
    expect(screen.getByText(/Every upgraded device came back/)).toBeInTheDocument();
    expect(screen.getByText('Deploy')).toBeInTheDocument();
  });
});

describe('configuration studio to deployment', () => {
  it('"Deploy this version…" opens a plan with the device and version chosen', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'd1', project_id: 'p1' });
    const v1 = { id: 'v1', device_id: 'd1', kind: 'imported', sha256: 'abcdef0123456789'.repeat(4), platform: '',
      template_version: '', verification: '', reference: 'site-file.pcc', created_by: 'tester',
      created_at: '2026-11-23T10:00:00Z', text: 'hostname "lab-sw"\n', inspection: null };
    mockApi({ '/devices': [sw], '/projects': [{ id: 'p1', name: 'Bench' }], '/devices/d1/configs': [v1],
      '/configs/v1': v1, '/projects/p1/devices': [sw], '/deployments': [] });
    renderAt('/configurations?device=d1&version=v1');
    await userEvent.click(await screen.findByRole('button', { name: 'Deploy this version…' }));
    expect(await screen.findByText('New deployment plan')).toBeInTheDocument();
    expect(screen.getByLabelText('Include sw1')).toBeChecked();
    // The plan's version field shows the version chosen in the Configuration Studio.
    expect(await screen.findByDisplayValue(/^imported · site-file\.pcc · /)).toBeInTheDocument();
  });
});

describe('audit trail', () => {
  it('shows every detail of an entry and filters on details', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const long = { message: 'x'.repeat(200), first_login_credentials_set: false, credential: 'approved login' };
    mockApi({ '/audit': [
      { id: 'a1', timestamp: '2026-11-23T13:00:00Z', actor: 'local-user', action: 'provisioning.console_bootstrap',
        target_type: 'device', target_id: 'c4e8e81f-0000', outcome: 'bootstrapped', details: long },
      { id: 'a2', timestamp: '2026-11-23T13:01:00Z', actor: 'local-user', action: 'device.check_reachability',
        target_type: 'device', target_id: 'c4e8e81f-0000', outcome: 'failed', details: { message: 'Authentication failed' } },
    ] });
    renderAt('/audit');
    await userEvent.type(await screen.findByLabelText('Filter audit events'), 'first_login');
    expect(screen.queryByText('device.check_reachability')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'All details' }));
    expect(await screen.findByText(/"first_login_credentials_set": false/)).toBeInTheDocument();
  });
});

describe('firmware repository', () => {
  it('an unverified image can be verified with the vendor checksum after upload', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const img = { id: 'fg', vendor: 'Fortinet', platform: 'fortios', version: '7.6.5', filename: 'FGT_101F.out',
      size_bytes: 1024, sha256: 'f3'.repeat(32), vendor_sha256: null, vendor_sha512: null, integrity_verified: false,
      compatible_models: ['FortiGate-101F'], min_from_version: null, release_notes: '', status: 'uploaded',
      approved_by: null, approved_at: null, created_by: 'tester', created_at: '2026-11-24T08:00:00Z' };
    const calls = mockApi({ '/firmware/images': [img], '/firmware/images/fg/checksum': { ...img, integrity_verified: true } });
    renderAt('/firmware');
    expect(await screen.findByLabelText(/Vendor checksum \(SHA-256 or SHA-512\)/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Add vendor checksum…' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Vendor checksum'), 'ab'.repeat(64));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Verify' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/firmware/images/fg/checksum'
      && JSON.parse(String(c.init?.body)).checksum === 'ab'.repeat(64))).toBe(true));
  });
});

describe('firmware approval without a vendor checksum', () => {
  it('needs a written reason and is shown as not verified afterwards', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const img = { id: 'fg', vendor: 'Fortinet', platform: 'fortios', version: '7.6.5', filename: 'FGT_101F.out',
      size_bytes: 1024, sha256: 'f3'.repeat(32), vendor_sha256: null, vendor_sha512: null, integrity_verified: false,
      unverified_reason: null, compatible_models: ['FortiGate-101F'], min_from_version: null, release_notes: '',
      status: 'uploaded', approved_by: null, approved_at: null, created_by: 'tester', created_at: '2026-11-24T08:00:00Z' };
    const reason = 'taken from our approved software store';
    const calls = mockApi({ '/firmware/images': [img],
      '/firmware/images/fg/approve': { ...img, status: 'approved', approved_by: 'tester', unverified_reason: reason } });
    renderAt('/firmware');
    await userEvent.click(await screen.findByRole('button', { name: 'Approve without checksum…' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Approve without checksum' });
    await userEvent.type(within(dialog).getByLabelText(/Reason for approving without the checksum/), 'short');
    expect(confirm).toBeDisabled();
    await userEvent.clear(within(dialog).getByLabelText(/Reason for approving without the checksum/));
    await userEvent.type(within(dialog).getByLabelText(/Reason for approving without the checksum/), reason);
    await userEvent.click(confirm);
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/firmware/images/fg/approve'
      && JSON.parse(String(c.init?.body)).unverified_reason === reason)).toBe(true));
  });

  it('marks an image approved with a reason', async () => {
    const img = { id: 'fg', vendor: 'Fortinet', platform: 'fortios', version: '7.6.5', filename: 'FGT_101F.out',
      size_bytes: 1024, sha256: 'f3'.repeat(32), vendor_sha256: null, vendor_sha512: null, integrity_verified: false,
      unverified_reason: 'taken from our approved software store', compatible_models: ['FortiGate-101F'],
      min_from_version: null, release_notes: '', status: 'approved', approved_by: 'tester',
      approved_at: '2026-11-24T08:10:00Z', created_by: 'tester', created_at: '2026-11-24T08:00:00Z' };
    mockApi({ '/firmware/images': [img] });
    renderAt('/firmware');
    expect(await screen.findByText('not verified · approved with reason')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add vendor checksum…' })).toBeInTheDocument();
  });
});

describe('staging plan', () => {
  const step = (n: number, state: string, extra: Record<string, unknown> = {}) => ({
    id: `dep${n}`, project_id: 'p', kind: 'configuration', state, dry_run: false, apply_mode: n === 1 ? 'replace' : 'merge',
    created_by: 'tester', approved_by: null, approved_at: null, created_at: '2026-11-24T10:00:00Z', updated_at: '2026-11-24T10:00:00Z',
    firmware_image_id: null, window_start: null, window_end: null, staging_id: 'sp1', staging_step: n, targets: [],
    events: [{ seq: 0, timestamp: '2026-11-24T10:00:00Z', stage: 'preview', status: 'ok',
      message: n === 2 ? 'preview deferred: it is made at the run, after step 1 has restored the base file' : '+10 -2 lines', device_id: null }],
    ...extra,
  });

  it('shows both steps and approves them with one action', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/staging-plans/sp1': { staging_id: 'sp1', steps: [step(1, 'awaiting_approval'), step(2, 'awaiting_approval')] },
      '/staging-plans/sp1/approve': { staging_id: 'sp1', steps: [step(1, 'ready'), step(2, 'ready')] },
    });
    renderAt('/staging/sp1');
    expect(await screen.findByText(/Step 1 · base file \(replace\)/)).toBeInTheDocument();
    expect(screen.getByText(/preview deferred/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Approve both steps' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/staging-plans/sp1/approve'
      && c.init?.method === 'POST')).toBe(true));
  });

  it('says why the site step did not run', async () => {
    mockApi({ '/staging-plans/sp1': { staging_id: 'sp1', steps: [step(1, 'recovery_required'), step(2, 'cancelled')] } });
    renderAt('/staging/sp1');
    expect(await screen.findByText('The plan did not complete')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Execute' })).not.toBeInTheDocument();
  });
});

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
    for (const label of ['Home', 'Systems', 'Devices', 'Files', 'Firmware', 'Console setup', 'Plans',
      'Advanced', 'Settings']) {
      expect(within(nav).getByText(label)).toBeInTheDocument();
    }
    // D-089: the safety switches are shown where they matter, not in the header.
    expect(screen.queryByText(/Real-device changes/)).not.toBeInTheDocument();
  });

  it('dashboard summarises inventory and deployments', async () => {
    mockApi({
      '/devices': [device({}), device({ id: 'd2', name: 'fw1', manufacturer: 'Fortinet', category: 'firewall', last_connection_at: '2026-01-01T00:00:00Z' })],
      '/projects': [{ id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '' }],
      '/deployments': [{ id: 'x', project_id: 'p1', state: 'awaiting_approval', dry_run: false, apply_mode: 'merge', created_by: 'a', approved_by: null, created_at: '2026-01-01T00:00:00Z' }],
    });
    renderAt('/');
    const waiting = (await screen.findByText('Waiting for you', { selector: 'p' })).parentElement!;
    expect(await within(waiting).findByText('1')).toBeInTheDocument();
    expect(screen.getByText('Read the preview and approve it')).toBeInTheDocument();
    expect(screen.getAllByText('Waiting for approval').length).toBeGreaterThan(0);
    expect(screen.getByText('0 of 2 up to date')).toBeInTheDocument();
  });

  it('inventory marks simulated devices and offers only read-only bulk actions', async () => {
    mockApi({ '/devices': [device({})], '/projects': [] });
    renderAt('/devices');
    expect(await screen.findByText('sw1')).toBeInTheDocument();
    expect(screen.getByText('Simulated')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Perform' })).toBeDisabled();
  });

  it('console setup page says which devices need none', async () => {
    mockApi({});
    renderAt('/provisioning');
    expect(await screen.findByText(/a First login\s+plan sets its approved password/)).toBeInTheDocument();
    expect(screen.queryByText(/not implemented/)).not.toBeInTheDocument();
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

  it('console setup starts from the port and address of the switch\'s wizard role', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'sys-sw-b', model: '2930F', role: 'Aruba 2930F (OOBM port 3)',
      driver_id: 'mock.aruba.aos_switch' });
    mockApi({
      '/devices': [sw],
      '/drivers': [{ driver_id: 'mock.aruba.aos_switch', platform: 'aos_switch', simulated: true, vendor: 'Aruba', os_family: 'ArubaOS-Switch', description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated switch console', hardware_id: '' }],
    });
    renderAt('/provisioning?device=sw');
    const port = await screen.findByLabelText(/Untagged port/);
    expect(port).toHaveValue('3');
    expect(screen.getByDisplayValue('192.168.1.2/24')).toBeInTheDocument();
    expect(screen.getByText('Stage a system: port 3 for this switch')).toBeInTheDocument();
    expect(screen.queryByText(/The bench cabling uses port 3/)).not.toBeInTheDocument();
    await userEvent.clear(port);
    await userEvent.type(port, '83');
    expect(screen.getByText(/The bench cabling uses port 3 for this switch/)).toBeInTheDocument();
  });

  it('erasing is blocked up front when the device\'s own login has no password', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'dmz-sw', driver_id: 'mock.aruba.aos_switch', credential_ref_id: 'factory',
      bootstrap_profile: { vlan_id: 222, vlan_name: 'OOBM_VLAN', untagged_port: '2', address: '192.168.1.1/24' } });
    mockApi({
      '/devices': [sw],
      '/drivers': [{ driver_id: 'mock.aruba.aos_switch', platform: 'aos_switch', simulated: true, vendor: 'Aruba', os_family: 'ArubaOS-Switch', description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated switch console', hardware_id: '' }],
      '/projects/p1/credential-refs': [{ id: 'factory', name: 'Aruba Factory', has_secret: true, empty_password: true }],
    });
    renderAt('/provisioning?device=sw');
    await userEvent.click(await screen.findByRole('button', { name: 'Run console bootstrap…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Run console bootstrap' });
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /preconfigured/ }));
    expect(within(dialog).getByText(/Its login "Aruba Factory" has no password/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Erase and bootstrap' })).toBeDisabled();
  });

  it('erasing a preconfigured switch: UNDM reads its name, the person confirms it (D-095)', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sw', name: 'dmz-sw', driver_id: 'mock.aruba.aos_switch', credential_ref_id: 'new',
      bootstrap_profile: { vlan_id: 222, vlan_name: 'OOBM_VLAN', untagged_port: '2', address: '192.168.1.1/24' } });
    const calls = mockApi({
      '/devices': [sw],
      '/drivers': [{ driver_id: 'mock.aruba.aos_switch', platform: 'aos_switch', simulated: true, vendor: 'Aruba', os_family: 'ArubaOS-Switch', description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated switch console', hardware_id: '' }],
      '/projects/p1/credential-refs': [{ id: 'old', name: 'preconfigured login' },
        { id: 'new', name: 'approved', has_secret: true, empty_password: false }],
      '/devices/sw/provisioning/console-identify': { state: 'configured', hostname: 'lab-bhdmz-sw01', message: '' },
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
    await userEvent.click(within(dialog).getByPlaceholderText('Choose its current login'));
    await userEvent.click((await screen.findAllByRole('option', { name: 'preconfigured login', hidden: true }))[0]);
    expect(within(dialog).queryByLabelText(/Type its current hostname/)).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Read its name from the console' }));
    const yes = await within(dialog).findByRole('checkbox', { name: /Yes, erase lab-bhdmz-sw01/ });
    expect(go).toBeDisabled();  // read, not yet confirmed
    await userEvent.click(yes);
    expect(go).toBeEnabled();
    expect(within(dialog).getByText('approved', { selector: 'b' })).toBeInTheDocument();  // its login after the erase
    const asked = calls.find((c) => c.url.endsWith('/provisioning/console-identify'));
    expect(JSON.parse(String(asked?.init?.body))).toEqual({ serial_port: 'SIMULATED', baudrate: 9600, current_credential_ref_id: 'old' });
    await userEvent.click(go);
    expect(await screen.findByText(/erased “lab-bhdmz-sw01” first/)).toBeInTheDocument();
    const sent = calls.find((c) => c.url.endsWith('/provisioning/console-bootstrap'));
    expect(JSON.parse(String(sent?.init?.body))).toMatchObject({ erase_existing: true,
      current_credential_ref_id: 'old', confirm_hostname: 'lab-bhdmz-sw01', allow_configured: false });
  });

  it('the switch state is shown next to Run for a real device, and not for a simulated one (D-089)', async () => {
    const pol = { enable_real_device_writes: false, enable_real_device_firmware: false, allow_production_read_only: false,
      allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: true, locked: [] };
    const dep = { id: 'dep1', project_id: 'p1', kind: 'configuration', state: 'ready', dry_run: false, apply_mode: 'merge',
      created_by: 'a', approved_by: 'b', created_at: '', updated_at: '', firmware_image_id: null, window_start: null,
      window_end: null, approved_at: null, targets: [{ device_id: 'd1', position: 0, config_version_id: null, backup_version_id: null,
        state: 'previewed', diff: '', message: '' }], events: [] };
    mockApi({ '/policy': pol, '/deployments/dep1': dep, '/projects/p1/devices': [device({ environment: 'lab', driver_id: 'ssh.aruba.aoscx' })] });
    const view = renderAt('/deployments/dep1');
    expect(await screen.findByText(/Real-device changes are off: real devices can only be read/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings → Safety' })).toHaveAttribute('href', '/settings?tab=safety');
    view.unmount();
    mockApi({ '/policy': pol, '/deployments/dep1': dep, '/projects/p1/devices': [device({})] });  // simulated
    renderAt('/deployments/dep1');
    expect(await screen.findByRole('button', { name: 'Run plan' })).toBeInTheDocument();
    expect(screen.queryByText(/Real-device changes are/)).not.toBeInTheDocument();
  });

  it('firmware page lists images with integrity status', async () => {
    mockApi({ '/firmware/images': [{
      id: 'i1', vendor: 'Aruba', platform: 'aoscx', version: '10.1.0', filename: 'cx.swi', size_bytes: 2048,
      sha256: 'a'.repeat(64), vendor_sha256: 'a'.repeat(64), integrity_verified: true, compatible_models: ['6300M'],
      min_from_version: null, release_notes: '', status: 'uploaded', approved_by: null, approved_at: null,
      created_by: 'x', created_at: '2026-01-01T00:00:00Z' }] });
    renderAt('/firmware');
    expect(await screen.findByText('cx.swi')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
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
    expect(screen.queryByText('This renames the device')).not.toBeInTheDocument();
    await userEvent.clear(field);
    await userEvent.type(field, 'other');
    expect(screen.getByText('This renames the device')).toBeInTheDocument();
  });
});

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

describe('deployment outcome', () => {
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
    const dialog = await screen.findByRole('dialog', { name: 'Stop this plan?' });
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
    await userEvent.click(await screen.findByRole('button', { name: 'View configuration after the plan' }));
    expect(await screen.findByText(/hostname "lab-sw"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare with what was sent' })).toBeInTheDocument();
  });

  it('a successful real upgrade keeps the upgrade wording', async () => {
    mockApi({ '/deployments/dep1': plan({ dry_run: false, approved_by: 'approver' }), '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    expect(await screen.findByText('Plan succeeded')).toBeInTheDocument();
    expect(screen.getByText(/Every upgraded device came back/)).toBeInTheDocument();
    expect(screen.getByText('Deploy')).toBeInTheDocument();
  });
});

describe('configuration studio to deployment', () => {
  it('"Make a plan with this version…" opens a plan with the device and version chosen', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'd1', project_id: 'p1' });
    const v1 = { id: 'v1', device_id: 'd1', kind: 'imported', sha256: 'abcdef0123456789'.repeat(4), platform: '',
      template_version: '', verification: '', reference: 'site-file.pcc', created_by: 'tester',
      created_at: '2026-11-23T10:00:00Z', text: 'hostname "lab-sw"\n', inspection: null };
    mockApi({ '/devices': [sw], '/projects': [{ id: 'p1', name: 'Bench' }], '/devices/d1/configs': [v1],
      '/configs/v1': v1, '/projects/p1/devices': [sw], '/deployments': [] });
    renderAt('/configurations?device=d1&version=v1');
    await userEvent.click(await screen.findByRole('button', { name: 'Make a plan with this version…' }));
    expect(await screen.findByText('New configuration plan')).toBeInTheDocument();
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
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('First login credentials set')).toBeInTheDocument();
    expect(within(dialog).getByText('approved login')).toBeInTheDocument();
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
    expect(await screen.findByText('Not verified · approved with reason')).toBeInTheDocument();
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

  it('shows every step and approves them with one action', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/staging-plans/sp1': { staging_id: 'sp1', steps: [step(1, 'awaiting_approval'), step(2, 'awaiting_approval')] },
      '/staging-plans/sp1/approve': { staging_id: 'sp1', steps: [step(1, 'ready'), step(2, 'ready')] },
    });
    renderAt('/staging/sp1');
    expect(await screen.findByText(/Step 1 · Complete file: the device fetches it/)).toBeInTheDocument();
    expect(screen.getByText(/preview deferred/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Approve all steps' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/staging-plans/sp1/approve'
      && c.init?.method === 'POST')).toBe(true));
  });

  it('says why the site step did not run', async () => {
    mockApi({ '/staging-plans/sp1': { staging_id: 'sp1', steps: [step(1, 'recovery_required'), step(2, 'cancelled')] } });
    renderAt('/staging/sp1');
    expect(await screen.findByText('The plan did not complete')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run' })).not.toBeInTheDocument();
  });
});

describe('Settings → Safety', () => {
  const policy = {
    enable_real_device_writes: false, enable_real_device_firmware: false, allow_production_read_only: false,
    allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: true, locked: [],
  };

  it('turning a switch on needs a confirmation; turning it off does not', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/policy': policy });
    renderAt('/settings?tab=safety');
    await userEvent.click(await screen.findByRole('switch', { name: 'Real-device changes' }));
    const dialog = await screen.findByRole('dialog');
    const go = within(dialog).getByRole('button', { name: 'Turn on' });
    expect(go).toBeDisabled();
    expect(calls.some((c) => c.init?.method === 'PUT')).toBe(false);
    await userEvent.click(within(dialog).getByLabelText('The devices are spare units on an isolated bench'));
    await userEvent.click(go);
    const put = calls.find((c) => c.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body))).toEqual({ enable_real_device_writes: true });
  });

  it('a switch fixed by the start-up settings cannot be changed here', async () => {
    mockApi({ '/policy': { ...policy, enable_real_device_writes: true, locked: ['enable_real_device_writes'] } });
    renderAt('/settings?tab=safety');
    expect(await screen.findByRole('switch', { name: 'Real-device changes' })).toBeDisabled();
    expect(screen.getByText(/Fixed in backend\\\.env/)).toBeInTheDocument();
    expect(screen.getByText('UNDM_ENABLE_REAL_DEVICE_WRITES')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Firmware changes' })).toBeEnabled();
  });
});

describe('plain words', () => {
  it('states, drivers and capabilities are shown in words', async () => {
    const { capabilityLabel, driverLabel, stateLabel } = await import('../src/services/labels');
    expect(stateLabel('awaiting_approval')).toBe('Waiting for approval');
    expect(stateLabel('recovery_required')).toBe('Needs attention');
    expect(stateLabel('some_new_state')).toBe('Some new state');
    expect(driverLabel('ssh.blackbox.lig1014a')).toBe('Black Box LIG1014A over SSH');
    expect(driverLabel('mock.aruba.aoscx')).toMatch(/^Simulated/);
    expect(capabilityLabel('supports_firmware_upgrade')).toBe('Upgrade its firmware');
  });
});

describe('confirmations', () => {
  it('cancelling a plan asks first, and an error stays inside the dialog', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/deployments/dep1': plan({ dry_run: false, state: 'awaiting_approval' }),
      '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel plan' }));
    const dialog = await screen.findByRole('dialog', { name: 'Cancel this plan?' });
    expect(calls.some((c) => c.url.endsWith('/cancel'))).toBe(false);
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: 'Synthetic refusal' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } })));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel plan' }));
    expect(await within(dialog).findByText('Synthetic refusal')).toBeInTheDocument();
  });

  it('deleting a system needs its name typed', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '', certificate_subject: null } });
    renderAt('/projects/p1');
    await userEvent.click(await screen.findByRole('tab', { name: 'System settings' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Delete system' }));
    const dialog = await screen.findByRole('dialog');
    const go = within(dialog).getByRole('button', { name: 'Delete system' });
    expect(go).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText('Type Lab A to confirm'), 'Lab A');
    expect(go).toBeEnabled();
    expect(calls.some((c) => c.init?.method === 'DELETE')).toBe(false);
  });
});

describe('Stage a system', () => {
  it('makes one plan for a device from the choices in the wizard', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    window.localStorage.setItem('undm.stage.p1', JSON.stringify({ blackbox: {
      firstLogin: true, imageId: null, allowDowngrade: false, alsoSecondary: false,
      baseId: null, siteId: null, fileId: 'v1', loginAfter: null, secrets: {} } }));
    const calls = mockApi({
      '/projects/p1': { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '', certificate_subject: null },
      '/projects/p1/devices': [device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A',
        driver_id: 'mock.blackbox.switch', management_address: '192.0.2.1' })],
      '/projects/p1/staging-plans': [],
    });
    renderAt('/stage/p1?step=3');
    expect(await screen.findByText('lab-a-bb')).toBeInTheDocument();
    expect(screen.getByText('1. Team file')).toBeInTheDocument();  // no firmware chosen: kept as it is
    await userEvent.click(screen.getByRole('button', { name: 'Make the plan' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1/device-staging')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/projects/p1/device-staging');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ device_id: 'bb', steps: [{ kind: 'configuration', version_id: 'v1' }] });
    window.localStorage.removeItem('undm.stage.p1');
  });

  const switches = () => [
    device({ id: 'sa', name: 'lab-a-sw-a', manufacturer: 'Aruba', model: '2930F', driver_id: 'mock.aruba.aos_switch',
      management_address: '192.168.1.1', provisioning_status: 'bootstrapped' }),
    device({ id: 'sb', name: 'lab-a-sw-b', manufacturer: 'Aruba', model: '2930F', driver_id: 'mock.aruba.aos_switch',
      management_address: '192.168.1.2', provisioning_status: 'bootstrapped' }),
  ];
  const project = { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '', certificate_subject: null };

  it('the bench check shows how each device is cabled and which 2930F waits (D-091)', async () => {
    mockApi({ '/projects/p1': project, '/projects/p1/devices': switches(), '/projects/p1/staging-plans': [] });
    renderAt('/stage/p1?step=2');
    const table = await screen.findByRole('table', { name: 'Cabling per device' });
    expect(within(table).getByText('USB console cable first; after its console setup, port 3 → small switch')).toBeInTheDocument();
    expect(within(table).getByText('same')).toBeInTheDocument();  // switch A keeps its address
    expect(screen.getByText(/lab-a-sw-b and lab-a-sw-a both end at 192\.168\.1\.1/)).toBeInTheDocument();
  });

  it('the bench check answers in the row: no login yet, or the reason a test was refused', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const real = (over: Record<string, unknown>) => device({ manufacturer: 'Aruba', model: '2930F',
      driver_id: 'ssh.aruba.aos_switch', environment: 'lab', provisioning_status: 'bootstrapped', ...over });
    mockApi({ '/projects/p1': project, '/projects/p1/staging-plans': [], '/projects/p1/devices': [
      real({ id: 'sa', name: 'lab-a-sw-a', management_address: '192.168.1.1', credential_ref_id: null }),
      real({ id: 'sb', name: 'lab-a-sw-b', management_address: '192.168.1.2', credential_ref_id: 'c1' }),
    ] });
    const fetchMock = vi.mocked(globalThis.fetch);
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => (String(input).includes('/operations/check_reachability')
      ? new Response(JSON.stringify({ error: 'lab-a-sw-b has no login chosen.' }), { status: 400, headers: { 'content-type': 'application/json' } })
      : answer(input, init)));
    const { MantineProvider } = await import('@mantine/core');
    const { Notifications } = await import('@mantine/notifications');
    const { render } = await import('@testing-library/react');
    render(<MantineProvider><Notifications /></MantineProvider>);  // where a pop-up would appear
    renderAt('/stage/p1?step=2');
    expect(await screen.findByText(/Choose its login first/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'step 1, “Its login”' })).toHaveAttribute('href', '/stage/p1?step=0');
    expect(screen.getAllByRole('button', { name: 'Test' })).toHaveLength(1);  // only the switch with a login
    await userEvent.click(screen.getByRole('button', { name: 'Test' }));
    expect(await screen.findByText('Did not connect')).toBeInTheDocument();
    expect(screen.getByText('lab-a-sw-b has no login chosen.')).toBeInTheDocument();
    expect(screen.queryByText('That did not work')).not.toBeInTheDocument();  // no pop-up over the table
  });

  it.each([
    [null, 'Expected now', /has no password yet/],
    ['2026-11-25T10:00:00Z', 'Did not connect', /The device refused the login/],
  ])('a factory FortiGate refusing the login is expected only before it ever connected (last connection %s)', async (last, badge, text) => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/projects/p1': project, '/projects/p1/staging-plans': [], '/projects/p1/devices': [
      device({ id: 'fw', name: 'lab-a-fw', manufacturer: 'Fortinet', model: 'FortiGate-101F', role: 'FortiGate 101F',
        driver_id: 'ssh.fortinet.fortios', environment: 'lab', management_address: '192.168.1.99',
        credential_ref_id: 'c1', last_connection_at: last }),
    ] });
    const fetchMock = vi.mocked(globalThis.fetch);
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => (String(input).includes('/operations/check_reachability')
      ? new Response(JSON.stringify({ status: 'failed', message: "The device refused the login (user 'admin').", data: null, login_refused: true }),
        { status: 200, headers: { 'content-type': 'application/json' } })
      : answer(input, init)));
    renderAt('/stage/p1?step=2');
    await userEvent.click(await screen.findByRole('button', { name: 'Test' }));
    expect(await screen.findByText(badge)).toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('the run board tells which switch to unplug before the other one loads its file', async () => {
    const choice = { firstLogin: true, imageId: null, allowDowngrade: false, alsoSecondary: false,
      baseId: null, siteId: null, fileId: 'v1', loginAfter: null, secrets: {} };
    window.localStorage.setItem('undm.stage.p1', JSON.stringify({ aruba_a: choice, aruba_b: choice }));
    mockApi({ '/projects/p1': project, '/projects/p1/devices': switches(), '/projects/p1/staging-plans': [] });
    renderAt('/stage/p1?step=3');
    expect(await screen.findByText(/where lab-a-sw-a answers\. Unplug lab-a-sw-a from the small switch/)).toBeInTheDocument();
    expect(screen.queryByText(/where lab-a-sw-b answers/)).not.toBeInTheDocument();
    window.localStorage.removeItem('undm.stage.p1');
  });

  it('without a system it offers to make or choose one', async () => {
    mockApi({});
    renderAt('/stage');
    expect(await screen.findByRole('heading', { name: 'Stage a system' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create and continue' })).toBeDisabled();
  });
});

describe('system packages', () => {
  it('after an import, says which logins need their passwords', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/projects': [],
      '/systems/import': { project: { id: 'p9', name: 'Site 12', description: '', site: '', purpose: '', created_at: '', updated_at: '' },
        summary: { devices: 4, files: 5, logins: ['approved', 'factory'], links: 0, firmware_added: 0, firmware_already_here: 0 } },
    });
    renderAt('/projects');
    await userEvent.click(await screen.findByRole('button', { name: 'Import…' }));
    const dialog = await screen.findByRole('dialog');
    const input = dialog.querySelector('input[type=file]') as HTMLInputElement;
    await userEvent.upload(input, new File(['PK'], 'site12.undm', { type: 'application/zip' }));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    expect(await within(dialog).findByText('Next: store the passwords')).toBeInTheDocument();
    expect(within(dialog).getByText('factory')).toBeInTheDocument();
    expect(calls.some((c) => c.url === '/api/systems/import' && c.init?.body instanceof FormData)).toBe(true);
  });
});

describe('plans that need attention (D-088)', () => {
  const row = (id: string, over: Record<string, unknown>) => ({ id, project_id: 'p1', kind: 'configuration', state: 'recovery_required',
    dry_run: false, apply_mode: 'replace', created_by: 'a', approved_by: 'b', created_at: '2026-11-23T10:00:00Z', ...over });

  it('Home lists only those still waiting for a check', async () => {
    mockApi({
      '/projects': [{ id: 'p1', name: 'Bench', description: '', site: '', purpose: '', created_at: '', updated_at: '' }],
      '/deployments': [row('old', { needs_attention: false, attention_cleared: 'superseded:new' }),
        row('open', { needs_attention: true, created_at: '2026-11-24T10:00:00Z' })],
    });
    renderAt('/');
    expect(await screen.findByText('Check the device: it may be half-changed')).toBeInTheDocument();
    expect(screen.getAllByText('Check the device: it may be half-changed')).toHaveLength(1);
    const stat = screen.getByText('Needs attention', { selector: 'p' }).parentElement!;
    expect(within(stat).getByText('1')).toBeInTheDocument();
    expect(screen.getByText('later plan succeeded')).toBeInTheDocument();
  });

  it('a plan is marked as checked with a note', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/deployments/dep1': plan({ dry_run: false, kind: 'configuration', state: 'recovery_required',
      needs_attention: true }), '/projects/p1/devices': [device({})] });
    renderAt('/deployments/dep1');
    await userEvent.click(await screen.findByRole('button', { name: 'Mark as checked…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Mark as checked' });
    await userEvent.type(within(dialog).getByLabelText(/What did you check/), 'console: running config matches');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Mark as checked' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/deployments/dep1/checked')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/deployments/dep1/checked');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ note: 'console: running config matches' });
  });
});

describe('deleting from lists', () => {
  it('devices are deleted from the list after their name or "delete" is typed', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/devices': [device({}), device({ id: 'd2', name: 'sw2' })], '/projects': [] });
    renderAt('/devices');
    await userEvent.click(await screen.findByLabelText('Select sw1'));
    await userEvent.click(screen.getByLabelText('Select sw2'));
    await userEvent.click(screen.getAllByLabelText('Bulk action')[0]);
    await userEvent.click(await screen.findByRole('option', { name: 'Delete devices…', hidden: true }));
    await userEvent.click(screen.getByRole('button', { name: 'Perform' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete 2 devices?' });
    const go = within(dialog).getByRole('button', { name: 'Delete' });
    expect(go).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText('Type delete to confirm'), 'delete');
    await userEvent.click(go);
    await vi.waitFor(() => expect(calls.filter((c) => c.init?.method === 'DELETE').map((c) => c.url))
      .toEqual(['/api/devices/d1', '/api/devices/d2']));
  });

  it('a finished plan can be deleted from the plans list', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/deployments': [{ id: 'x1', project_id: 'p1', kind: 'configuration', state: 'succeeded', dry_run: false,
      apply_mode: 'merge', created_by: 'a', approved_by: 'b', created_at: '2026-11-23T10:00:00Z' }], '/projects': [] });
    renderAt('/deployments');
    await userEvent.click(await screen.findByLabelText(/Delete plan of/));
    const dialog = await screen.findByRole('dialog', { name: 'Delete this plan?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/deployments/x1' && c.init?.method === 'DELETE')).toBe(true));
  });
});

describe('bench log (D-090)', () => {
  it('shows the masked log for reading, with copy and download', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calls.push(url);
      if (url.includes('/bench-log')) return new Response('UNDM bench log (masked)\nsystem: <system-1>\n', { status: 200 });
      const body = url.endsWith('/projects/p1')
        ? { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '', certificate_subject: null } : [];
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    renderAt('/projects/p1');
    await userEvent.click(await screen.findByRole('button', { name: 'Bench log…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Bench log' });
    expect(await within(dialog).findByText(/system: <system-1>/)).toBeInTheDocument();
    expect(within(dialog).getByText('Read it through before sharing')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Download .txt' })).toBeEnabled();
    expect(calls.some((u) => u === '/api/projects/p1/bench-log?hours=48')).toBe(true);
  });
});

describe('For all systems (D-105)', () => {
  const login = (id: string, name: string, over: Record<string, unknown> = {}) =>
    ({ id, name, provider: 'keyring', locator: `credential/${id}`, has_secret: true, empty_password: false, shared: true, ...over });
  const defaults = {
    firewall: { login: 'ok', login_after: 'base', tunnel_key: 'psk' },
    blackbox: { login: 'bbf', login_after: 'ok' },
    aruba: { login: 'ok', current: 'arf' },
  };
  const project = { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '', certificate_subject: null };

  it('Settings stores the logins, the default login per device and the certificate answers once', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/credential-refs': [login('ok', 'approved'), login('arf', 'aruba factory', { empty_password: true })],
      '/settings/defaults': { firewall: { login: null, login_after: null, tunnel_key: null },
        blackbox: { login: null, login_after: null }, aruba: { login: null, current: null } },
      '/settings/certificate': { subject: null },
    });
    renderAt('/settings');
    expect(await screen.findByRole('tab', { name: 'For all systems', selected: true })).toBeInTheDocument();
    expect(await screen.findByRole('cell', { name: 'approved' })).toBeInTheDocument();
    const label = screen.getByText('Login it has now (console setup)').closest('label')!;
    await userEvent.click(document.getElementById(label.htmlFor)!);
    const list = document.getElementById(document.getElementById(label.htmlFor)!.getAttribute('aria-controls')!)!;
    await userEvent.click(within(list).getByRole('option', { name: 'aruba factory', hidden: true }));
    await userEvent.click(screen.getByRole('button', { name: 'Save default logins' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/defaults' && c.init?.method === 'PUT')).toBe(true));
    const put = calls.find((c) => c.url === '/api/settings/defaults' && c.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body)).aruba).toEqual({ login: null, current: 'arf' });
    await userEvent.type(screen.getAllByLabelText(/Common Name/)[0], 'lab-cn');
    await userEvent.click(screen.getByRole('button', { name: 'Save certificate answers' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/certificate' && c.init?.method === 'PUT')).toBe(true));
    const cert = calls.find((c) => c.url === '/api/settings/certificate' && c.init?.method === 'PUT');
    expect(JSON.parse(String(cert?.init?.body)).subject.common_name).toBe('lab-cn');
  });

  it('the wizard adds a real device with its default login and fills the ones without', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/projects/p1': project, '/settings/defaults': defaults, '/projects/p1/staging-plans': [],
      '/projects/p1/credential-refs': [login('ok', 'approved'), login('bbf', 'bb factory')],
      '/device-models': [{ model_id: 'aruba-2930f', manufacturer: 'Aruba', product_family: '2930F', model: '2930F', category: 'switch', os_family: 'ArubaOS-Switch', drivers: [], support: 'lab_validated', notes: '' },
        { model_id: 'fortinet-fg-101f', manufacturer: 'Fortinet', product_family: 'FortiGate', model: 'FortiGate-101F', category: 'firewall', os_family: 'FortiOS', drivers: [], support: 'lab_validated', notes: '' }],
      '/projects/p1/devices': [device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A', role: 'Black Box LIG1014A',
        driver_id: 'ssh.blackbox.lig1014a', environment: 'lab', management_address: '192.0.2.1', credential_ref_id: null })],
    });
    renderAt('/stage/p1?step=0');
    await userEvent.click(await screen.findByRole('button', { name: /Use the default logins \(1 device\)/ }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/bb' && c.init?.method === 'PATCH')).toBe(true));
    const patch = calls.find((c) => c.url === '/api/devices/bb' && c.init?.method === 'PATCH');
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ credential_ref_id: 'bbf' });
    await userEvent.click(screen.getByRole('button', { name: 'Add it (192.168.1.99)' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1/devices' && c.init?.method === 'POST')).toBe(true));
    const add = calls.find((c) => c.url === '/api/projects/p1/devices' && c.init?.method === 'POST');
    expect(JSON.parse(String(add?.init?.body))).toMatchObject({ role: 'FortiGate 101F', credential_ref_id: 'ok' });
  });

  it('step 2 starts with the login after loading for all systems, once', async () => {
    window.localStorage.removeItem('undm.stage.p1');
    mockApi({
      '/projects/p1': project, '/settings/defaults': defaults, '/projects/p1/staging-plans': [],
      '/projects/p1/credential-refs': [login('ok', 'approved'), login('bbf', 'bb factory')],
      '/projects/p1/devices': [device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A', role: 'Black Box LIG1014A',
        driver_id: 'ssh.blackbox.lig1014a', environment: 'lab', management_address: '192.0.2.1', credential_ref_id: 'bbf' })],
    });
    renderAt('/stage/p1?step=1');
    expect(await screen.findByDisplayValue('approved')).toBeInTheDocument();
    await vi.waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem('undm.stage.p1') ?? '{}');
      expect(stored.blackbox).toMatchObject({ loginAfter: 'ok', filled: ['loginAfter'] });
    });
    window.localStorage.removeItem('undm.stage.p1');
  });

  it('the console setup starts with the login it has now from the defaults', async () => {
    const sw = device({ id: 'sw', name: 'lab-sw', model: '2930F', role: 'Aruba 2930F (OOBM port 2)', driver_id: 'ssh.aruba.aos_switch',
      environment: 'lab', credential_ref_id: 'ok' });
    mockApi({
      '/devices': [sw], '/settings/defaults': defaults,
      '/drivers': [{ driver_id: 'ssh.aruba.aos_switch', platform: 'aos_switch', simulated: false, vendor: 'Aruba', os_family: 'ArubaOS-Switch', description: '', capabilities: [], maturity: 'experimental', transport: 'ssh', notes: [] }],
      '/projects/p1/credential-refs': [login('ok', 'approved'), login('arf', 'aruba factory', { empty_password: true })],
      '/provisioning/serial-ports': [{ port: 'COM7', description: 'USB Serial', hardware_id: '' }],
      '/policy': { enable_real_device_writes: true, enable_real_device_firmware: false, allow_production_read_only: false,
        allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: false, locked: [] },
    });
    const { default: userEvent } = await import('@testing-library/user-event');
    renderAt('/provisioning?device=sw');
    await userEvent.click(await screen.findByPlaceholderText('Choose the console cable’s port'));
    await userEvent.click((await screen.findAllByRole('option', { name: /COM7/, hidden: true }))[0]);
    await userEvent.click(await screen.findByRole('button', { name: 'Run console bootstrap…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Run console bootstrap' });
    expect(within(dialog).getByDisplayValue('aruba factory')).toBeInTheDocument();
  });

  it('a system lists the logins for all systems read-only, and its certificate uses the shared answers', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({
      '/projects/p1': project, '/projects/p1/devices': [], '/projects/p1/deployments': [],
      '/projects/p1/credential-refs': [login('own', 'local', { shared: false }), login('ok', 'approved')],
      '/settings/certificate': { subject: { common_name: 'lab-cn', org_unit: '', org_name: '', locality: '', state: '', country: '',
        profile_name: 'Profile', certificate_name: 'certificate' } },
    });
    renderAt('/projects/p1');
    await userEvent.click(await screen.findByRole('tab', { name: 'Logins' }));
    expect(await screen.findByText('all systems')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete local' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete approved' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'System settings' }));
    expect(await screen.findByText(/uses the answers for all systems/)).toBeInTheDocument();
  });
});

describe('finishing a system (D-108)', () => {
  const project = (over: Record<string, unknown> = {}) => ({ id: 'p1', name: 'Lab A', description: '', site: '', purpose: '',
    created_at: '', updated_at: '', certificate_subject: null, staged_at: null, staged_by: '', ...over });
  const bb = (over: Record<string, unknown> = {}) => device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A',
    role: 'Black Box LIG1014A', driver_id: 'mock.blackbox.switch', management_address: '192.0.2.1', ...over });
  const plan = { staging_id: 'sp1', steps: [{ id: 'd1', project_id: 'p1', kind: 'configuration', state: 'succeeded', dry_run: false,
    apply_mode: 'replace', created_by: 't', approved_by: 't', approved_at: null, created_at: '', updated_at: '', firmware_image_id: null,
    window_start: null, window_end: null, staging_id: 'sp1', staging_step: 1, targets: [], events: [] }] };
  const policyOn = { enable_real_device_writes: true, enable_real_device_firmware: true, allow_production_read_only: false,
    allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: false, locked: [] };

  it('a checklist leads to Finish staging, which UNDM records', async () => {
    window.localStorage.removeItem('undm.finish.p1');
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/projects/p1': project(), '/projects/p1/devices': [bb()], '/policy': policyOn, '/staging-plans/sp1': plan,
      '/projects/p1/staging-plans': [{ staging_id: 'sp1', device_id: 'bb', created_at: '', kinds: ['configuration'], states: ['succeeded'] }],
      '/projects/p1/finish': project({ staged_at: '2026-11-26T09:00:00Z', staged_by: 'tester' }),
    });
    renderAt('/stage/p1?step=4');
    const finish = await screen.findByRole('button', { name: 'Finish staging' });
    expect(await screen.findByText('The latest staging plan of each device succeeded.')).toBeInTheDocument();
    expect(finish).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Turn them off' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/policy' && c.init?.method === 'PUT')).toBe(true));
    const put = calls.find((c) => c.url === '/api/policy' && c.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body))).toEqual({ enable_real_device_writes: false, enable_real_device_firmware: false });
    for (const name of ['Report saved', 'Backups downloaded', 'Devices powered off and labelled']) {
      await userEvent.click(screen.getByRole('checkbox', { name }));
    }
    expect(JSON.parse(window.localStorage.getItem('undm.finish.p1') ?? '{}')).toEqual({ report: true, backups: true, powered: true });
    expect(finish).toBeDisabled();  // the safety switches are still on (the mock answers with the old policy)
  });

  it('with everything ticked, Finish staging sends the staged devices', async () => {
    window.localStorage.setItem('undm.finish.p1', JSON.stringify({ report: true, backups: true, powered: true }));
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/projects/p1': project(), '/projects/p1/devices': [bb()], '/staging-plans/sp1': plan,
      '/policy': { ...policyOn, enable_real_device_writes: false, enable_real_device_firmware: false },
      '/projects/p1/staging-plans': [{ staging_id: 'sp1', device_id: 'bb', created_at: '', kinds: ['configuration'], states: ['succeeded'] }],
      '/projects/p1/finish': project({ staged_at: '2026-11-26T09:00:00Z', staged_by: 'tester' }),
    });
    renderAt('/stage/p1?step=4');
    const finish = await screen.findByRole('button', { name: 'Finish staging' });
    await vi.waitFor(() => expect(finish).toBeEnabled());
    await userEvent.click(finish);
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1/finish')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/projects/p1/finish');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ device_ids: ['bb'] });
    window.localStorage.removeItem('undm.finish.p1');
  });

  it('a switch with its port off must be switched off and on first', async () => {
    const calls = mockApi({
      '/projects/p1': project(), '/policy': { ...policyOn, enable_real_device_writes: false, enable_real_device_firmware: false },
      '/projects/p1/devices': [device({ id: 'sa', name: 'lab-a-sw-a', model: '2930F', role: 'Aruba 2930F (OOBM port 2)',
        driver_id: 'mock.aruba.aos_switch', management_address: '192.168.1.1',
        observed_facts: { extra: { management_port_off: { port: '2', since: '' } } } as never })],
      '/projects/p1/staging-plans': [],
    });
    renderAt('/stage/p1?step=4');
    expect(await screen.findByText(/port 2 is on again/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Test' })).not.toBeInTheDocument();
    const { default: userEvent } = await import('@testing-library/user-event');
    await userEvent.click(screen.getByRole('button', { name: 'It was switched off and on' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/sa/port-off/clear')).toBe(true));
  });

  it('safety switches fixed in backend\\.env say which lines to delete', async () => {
    mockApi({
      '/projects/p1': project(), '/projects/p1/devices': [bb()], '/staging-plans/sp1': plan,
      '/policy': { ...policyOn, locked: ['enable_real_device_writes', 'enable_real_device_firmware'] },
      '/projects/p1/staging-plans': [{ staging_id: 'sp1', device_id: 'bb', created_at: '', kinds: ['configuration'], states: ['succeeded'] }],
    });
    renderAt('/stage/p1?step=4');
    expect(await screen.findByText(/Fixed on in backend\\\.env/)).toBeInTheDocument();
    expect(screen.getByText('UNDM_ENABLE_REAL_DEVICE_WRITES')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Turn them off' })).not.toBeInTheDocument();
  });

  it('a finished system says so, with Reopen, and its stepper is complete', async () => {
    mockApi({
      '/projects/p1': project({ staged_at: '2026-11-26T09:00:00Z', staged_by: 'tester' }), '/projects/p1/devices': [bb()],
      '/staging-plans/sp1': plan,
      '/projects/p1/staging-plans': [{ staging_id: 'sp1', device_id: 'bb', created_at: '', kinds: ['configuration'], states: ['succeeded'] }],
    });
    renderAt('/stage/p1?step=4');
    expect(await screen.findByText(/^Staging finished · .* by tester$/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reopen' })).toBeInTheDocument();
    expect(screen.getByText(/^finished /)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Finish staging' })).not.toBeInTheDocument();
  });
});

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
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({});
    renderAt('/');
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    // D-120: three groups; the engineers' pages are folded under Advanced until opened.
    for (const label of ['Work', 'Home', 'Stage a system', 'Systems', 'Setup', 'Firmware', 'Settings']) {
      expect(within(nav).getByText(label)).toBeVisible();
    }
    expect(within(nav).getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
    const advanced = within(nav).getByRole('button', { name: 'Advanced' });
    expect(advanced).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(advanced);
    expect(advanced).toHaveAttribute('aria-expanded', 'true');
    for (const label of ['Devices (all systems)', 'Plans', 'Console tool', 'Topology', 'Audit log']) {
      expect(await within(nav).findByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole('link', { name: 'Plans' })).toHaveAttribute('href', '/plans');
    // D-089: the safety switches are shown where they matter, not in the header.
    expect(screen.queryByText(/Real-device changes/)).not.toBeInTheDocument();
  });

  it('old addresses move to their new place and keep their query (D-120)', async () => {
    mockApi({ '/projects/p1': { id: 'p1', name: 'Lab A' }, '/devices/d1': device({ id: 'd1' }) });
    const cases: [string, string][] = [
      ['/projects', '/systems'],
      ['/projects/p1', '/systems/p1'],
      ['/deployments', '/plans'],
      ['/deployments?project=p1&devices=d1&version=v1', '/plans/new?devices=d1&version=v1&system=p1'],
      ['/deployments/dep1', '/plans/dep1'],
      ['/staging/sp1', '/plans/staging/sp1'],
      ['/provisioning?device=d1', '/console?device=d1'],
      ['/configurations?device=d1&version=v1', '/devices/d1?tab=files&version=v1'],
      ['/configurations', '/devices'],
    ];
    for (const [old, now] of cases) {
      const view = renderAt(old);
      await vi.waitFor(() => expect(view.here()).toBe(now));
      view.unmount();
    }
  });

  it('an address UNDM does not have says so and offers a way on', async () => {
    mockApi({});
    renderAt('/no-such-page');
    expect(await screen.findByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Home' })).toHaveAttribute('href', '/');
  });

  it('Stage a system goes back to the unfinished system and step; the chooser is one link away', async () => {
    window.localStorage.setItem('undm.wizard.last', 'p1');
    window.localStorage.setItem('undm.wizard.p1', JSON.stringify({ step: 2, mode: 'simulated' }));
    mockApi({ '/projects': [{ id: 'p1', name: 'Lab A', staged_at: null }] });
    const view = renderAt('/stage');
    await vi.waitFor(() => expect(view.here()).toBe('/stage/p1?step=2'));
    view.unmount();
    const chooser = renderAt('/stage?choose=1');
    expect(await screen.findByText('A system you have')).toBeInTheDocument();
    expect(chooser.here()).toBe('/stage?choose=1');
    chooser.unmount();
    // A finished system is not resumed.
    mockApi({ '/projects': [{ id: 'p1', name: 'Lab A', staged_at: '2026-11-26T10:00:00Z' }] });
    const done = renderAt('/stage');
    expect(await screen.findByText('A system you have')).toBeInTheDocument();
    expect(done.here()).toBe('/stage');
    window.localStorage.removeItem('undm.wizard.last');
    window.localStorage.removeItem('undm.wizard.p1');
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
    renderAt('/console');
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
    renderAt('/console?device=sw');
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
    renderAt('/console?device=sw');
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
    renderAt('/console?device=sw');
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
    renderAt('/console?device=sw');
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
    const view = renderAt('/plans/dep1');
    expect(await screen.findByText(/Real-device changes are off: real devices can only be read/)).toBeInTheDocument();
    // D-121: it can be turned on right here, with the same confirmation as in Settings.
    const { default: userEvent } = await import('@testing-library/user-event');
    await userEvent.click(screen.getByRole('button', { name: 'Turn real-device changes on…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Real-device changes: turn on?' });
    expect(within(dialog).getByRole('button', { name: 'Turn on' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    view.unmount();
    mockApi({ '/policy': pol, '/deployments/dep1': dep, '/projects/p1/devices': [device({})] });  // simulated
    renderAt('/plans/dep1');
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
    await userEvent.click(await screen.findByRole('tab', { name: 'Intended settings' }));
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
    await userEvent.click(await screen.findByRole('tab', { name: 'Intended settings' }));
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
    renderAt('/plans/dep1');
    expect(await screen.findByText('Dry run succeeded')).toBeInTheDocument();
    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument();
    expect(screen.queryByText(/Every upgraded device came back/)).not.toBeInTheDocument();
    expect(screen.queryByText('Deploy')).not.toBeInTheDocument();
    expect(screen.queryByText('Back up')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy events as text' })).toBeInTheDocument();
    expect(screen.getByText('Backup slot too')).toBeInTheDocument();  // D-123: one word for it
  });

  it('a running deployment can be stopped after a confirmation', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/deployments/dep1': plan({ dry_run: false, state: 'deploying', approved_by: 'approver' }),
      '/projects/p1/devices': [device({})] });
    renderAt('/plans/dep1');
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
    renderAt('/plans/dep1');
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
    renderAt('/plans/dep1');
    await userEvent.click(await screen.findByText('sw1'));
    await userEvent.click(await screen.findByRole('button', { name: 'View configuration after the plan' }));
    expect(await screen.findByText(/hostname "lab-sw"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare with what was sent' })).toBeInTheDocument();
  });

  it('a successful real upgrade keeps the upgrade wording', async () => {
    mockApi({ '/deployments/dep1': plan({ dry_run: false, approved_by: 'approver' }), '/projects/p1/devices': [device({})] });
    renderAt('/plans/dep1');
    expect(await screen.findByText('Plan succeeded')).toBeInTheDocument();
    expect(screen.getByText(/Every upgraded device came back/)).toBeInTheDocument();
    expect(screen.getByText('Change')).toBeInTheDocument();  // the stepper's plain words (D-123)
  });
});

describe('configuration studio to deployment', () => {
  it('"Make a plan with this version…" opens a plan with the device and version chosen', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'd1', project_id: 'p1' });
    const v1 = { id: 'v1', device_id: 'd1', kind: 'imported', sha256: 'abcdef0123456789'.repeat(4), platform: '',
      template_version: '', verification: '', reference: 'site-file.pcc', created_by: 'tester',
      created_at: '2026-11-23T10:00:00Z', text: 'hostname "lab-sw"\n', inspection: null };
    mockApi({ '/devices': [sw], '/devices/d1': sw, '/projects': [{ id: 'p1', name: 'Bench' }], '/projects/p1': { id: 'p1', name: 'Bench' },
      '/devices/d1/configs': [v1], '/configs/v1': v1, '/projects/p1/devices': [sw], '/deployments': [] });
    // The Files page of before D-120: the address now opens the device's Files tab with the version chosen.
    renderAt('/configurations?device=d1&version=v1');
    expect(await screen.findByRole('tab', { name: 'Files', selected: true })).toBeInTheDocument();
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
    renderAt('/plans/staging/sp1');
    expect(await screen.findByText(/Step 1 · Complete file: the device fetches it/)).toBeInTheDocument();
    expect(screen.getByText(/preview deferred/)).toBeInTheDocument();
    // D-121: the same approval dialog everywhere; engineers approve here without running.
    await userEvent.click(screen.getByRole('button', { name: 'Approve all steps…' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/staging-plans/sp1/approve'
      && c.init?.method === 'POST')).toBe(true));
  });

  it('says why the site step did not run', async () => {
    mockApi({ '/staging-plans/sp1': { staging_id: 'sp1', steps: [step(1, 'recovery_required'), step(2, 'cancelled')] } });
    renderAt('/plans/staging/sp1');
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
    renderAt('/plans/dep1');
    // D-122: under the plan's More menu.
    await userEvent.click(await screen.findByRole('button', { name: 'More actions' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Cancel plan…' }));
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
    renderAt('/systems/p1');
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
      '/projects/p1/device-staging': { staging_id: 'sp9', steps: [] },
    });
    renderAt('/stage/p1?step=3');
    expect(await screen.findByText('lab-a-bb')).toBeInTheDocument();
    expect(screen.getByText('1. Team file')).toBeInTheDocument();  // no firmware chosen: kept as it is
    // D-121: "Check and run" makes the plan (that changes nothing) and opens the decision.
    await userEvent.click(screen.getByRole('button', { name: 'Check and run…' }));
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
    renderAt('/systems');
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
    renderAt('/plans/dep1');
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
    renderAt('/plans');
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
    renderAt('/systems/p1');
    // D-122: under the system page's More menu.
    await userEvent.click(await screen.findByRole('button', { name: 'More actions' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Bench log…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Bench log' });
    expect(await within(dialog).findByText(/system: <system-1>/)).toBeInTheDocument();
    expect(within(dialog).getByText('Read it through before sharing')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Download .txt' })).toBeEnabled();
    expect(calls.some((u) => u === '/api/projects/p1/bench-log?hours=48')).toBe(true);
  });
});

describe('Settings for all systems (D-105, D-120)', () => {
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
    expect(await screen.findByRole('tab', { name: 'Logins', selected: true })).toBeInTheDocument();
    expect(await screen.findByRole('cell', { name: 'approved' })).toBeInTheDocument();
    const label = screen.getByText('Login it has now (console setup)').closest('label')!;
    await userEvent.click(document.getElementById(label.htmlFor)!);
    const list = document.getElementById(document.getElementById(label.htmlFor)!.getAttribute('aria-controls')!)!;
    await userEvent.click(within(list).getByRole('option', { name: 'aruba factory', hidden: true }));
    await userEvent.click(screen.getByRole('button', { name: 'Save default logins' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/defaults' && c.init?.method === 'PUT')).toBe(true));
    const put = calls.find((c) => c.url === '/api/settings/defaults' && c.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body)).aruba).toEqual({ login: null, current: 'arf' });
    await userEvent.click(screen.getByRole('tab', { name: 'Certificate' }));
    await userEvent.type((await screen.findAllByLabelText(/Common Name/))[0], 'lab-cn');
    await userEvent.click(screen.getByRole('button', { name: 'Save certificate answers' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/certificate' && c.init?.method === 'PUT')).toBe(true));
    const cert = calls.find((c) => c.url === '/api/settings/certificate' && c.init?.method === 'PUT');
    expect(JSON.parse(String(cert?.init?.body)).subject.common_name).toBe('lab-cn');
  });

  it('brings the systems\' own logins here under names the person can change (D-115)', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const groups = [
      { id: 'a-appr', name: 'Aruba 2930F – manager', existing: false, devices: 3,
        members: [{ id: 'a-appr', name: 'approved', system: 'Lab A', devices: 2 }, { id: 'b-appr', name: 'approved', system: 'Lab B', devices: 1 }] },
      { id: 'tk', name: 'FortiGate tunnel key', existing: true, devices: 0,
        members: [{ id: 'b-psk', name: 'psk', system: 'Lab B', devices: 0 }] },
    ];
    mockApi({ '/credential-refs': [], '/credential-refs/from-systems': groups, '/settings/certificate': { subject: null },
      '/settings/defaults': { firewall: { login: null, login_after: null, tunnel_key: null }, blackbox: { login: null, login_after: null }, aruba: { login: null, current: null } } });
    const answered = globalThis.fetch;
    const posted: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/credential-refs/from-systems' && init?.method === 'POST') {
        posted.push(JSON.parse(String(init.body)));
        return Promise.resolve(new Response(JSON.stringify({ logins: groups, replaced: { 'b-appr': 'a-appr', 'b-psk': 'tk' } }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return answered(url, init);
    }));
    window.localStorage.setItem('undm.stage.p2', JSON.stringify({ blackbox: { loginAfter: 'b-appr', secrets: {} },
      firewall: { loginAfter: null, secrets: { 'vpn > psksecret': 'b-psk' } } }));
    renderAt('/settings');
    expect(await screen.findByText(/2 systems still have 3 logins of their own/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Bring them here…' }));
    const dialog = await screen.findByRole('dialog');
    const name = within(dialog).getByLabelText('Name for approved, approved');
    expect(name).toHaveValue('Aruba 2930F – manager');
    expect(within(dialog).getByText('already here: joins it')).toBeInTheDocument();
    await userEvent.clear(name);
    expect(within(dialog).getByRole('button', { name: 'Bring 3 logins here' })).toBeDisabled();
    await userEvent.type(name, 'Approved manager login');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Bring 3 logins here' }));
    await vi.waitFor(() => expect(posted).toEqual([{ names: { 'a-appr': 'Approved manager login' } }]));
    await vi.waitFor(() => expect(JSON.parse(window.localStorage.getItem('undm.stage.p2')!)).toMatchObject({
      blackbox: { loginAfter: 'a-appr' }, firewall: { secrets: { 'vpn > psksecret': 'tk' } } }));
    window.localStorage.removeItem('undm.stage.p2');
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
    renderAt('/console?device=sw');
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
    renderAt('/systems/p1');
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
      '/policy': { ...policyOn, enable_real_device_writes: false, enable_real_device_firmware: false, firmware_require_separate_approver: true },
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

describe('files from the team templates (D-111)', () => {
  const project = (over: Record<string, unknown> = {}) => ({ id: 'p1', name: 'Lab z045', description: '', site: '', purpose: '',
    created_at: '', updated_at: '', certificate_subject: null, staged_at: null, staged_by: '', zone: null, ...over });
  const sw = (id: string, role: string) => device({ id, name: `lab-${id}`, manufacturer: 'Aruba', model: '2930F', role,
    driver_id: 'mock.aruba.aos_switch', management_address: '192.168.1.1' });
  const tpl = (role: string) => ({ id: `t-${role}`, role, version: 'v03', filename: '${zone_tag}-x-v03.pcc', reference_zone: 41,
    counts: {}, verified_zone: 42, line_ending: 'crlf', final_newline: false, created_by: 't', created_at: '', older: 0 });

  it('the zone starts from the system name and is saved on the system by itself (D-121)', async () => {
    const calls = mockApi({ '/projects/p1': project(), '/projects/p1/devices': [], '/projects/p1/staging-plans': [] });
    renderAt('/stage/p1?step=0');
    expect(await screen.findByDisplayValue('45')).toBeInTheDocument();
    expect(screen.getByText('z045 · 10.172.x · 10.45.x · 10.0.45.x · 130.45.x')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1' && c.init?.method === 'PATCH')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/projects/p1' && c.init?.method === 'PATCH');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ zone: 45, system_id: null });
  });

  it('Generate makes the files and chooses them; Compare shows the result per device', async () => {
    window.localStorage.removeItem('undm.stage.p1');
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/projects/p1': project({ zone: 45 }), '/projects/p1/staging-plans': [],
      '/projects/p1/devices': [sw('a', 'Aruba 2930F (OOBM port 2)'), sw('b', 'Aruba 2930F (OOBM port 3)')],
      '/templates': [tpl('bhdmz')],
      '/projects/p1/generate-files': [{ role: 'bhdmz', device_id: 'a', version_id: 'v-new', filename: 'z045-x-v03.pcc',
        template_version: 'v03', verified_zone: 42 }],
      '/projects/p1/compare-files': [{ role: 'bhdmz', device_id: 'a', generated_name: 'z045-x-v03.pcc', file_name: 'z045-x-v03.pcc',
        same: false, lines: 16, differences: [[6, 'logging 10.172.201.65', 'logging 10.1.1.1']] }],
    });
    renderAt('/stage/p1?step=1');
    expect(await screen.findByText(/No template for: LTE switch/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Generate the files for zone 45' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1/generate-files')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/projects/p1/generate-files');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ assignments: { bhdmz: 'a' } });
    await vi.waitFor(() => expect(JSON.parse(window.localStorage.getItem('undm.stage.p1') ?? '{}').aruba_a?.fileId).toBe('v-new'));
    await userEvent.click(screen.getByRole('button', { name: 'Compare with the devices\' files' }));
    expect(await screen.findByText('differs')).toBeInTheDocument();
    expect(screen.getByText(/line 6: template “logging 10.172.201.65” · file “logging 10.1.1.1”/)).toBeInTheDocument();
    window.localStorage.removeItem('undm.stage.p1');
  });

  it('Settings lists each template and what it was checked against', async () => {
    mockApi({ '/templates': [tpl('bhdmz')], '/credential-refs': [], '/settings/certificate': { subject: null },
      '/settings/pci-mapping': null });
    renderAt('/settings?tab=templates');
    const table = await screen.findByText('BH-DMZ switch (2930F, OOBM port 2)');
    expect(table).toBeInTheDocument();
    expect(await screen.findByText('against zone 42')).toBeInTheDocument();
    // Six templates not imported, and the PCI table not imported either.
    await vi.waitFor(() => expect(screen.getAllByText('not imported').length).toBe(7));
    expect(screen.getByText('Windows line endings (CRLF) · no final line break')).toBeInTheDocument();
  });

  it('downloads the files byte for byte: all for the zone from the wizard, one per template in Settings', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
    const calls = mockApi({
      '/projects/p1': project({ zone: 45 }), '/projects/p1/staging-plans': [],
      '/projects/p1/devices': [sw('a', 'Aruba 2930F (OOBM port 2)')], '/templates': [tpl('bhdmz')],
      '/credential-refs': [], '/settings/certificate': { subject: null }, '/settings/pci-mapping': null,
    });
    const view = renderAt('/stage/p1?step=1');
    await userEvent.click(await screen.findByRole('button', { name: 'Download the files for zone 45' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1/files.zip')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/projects/p1/files.zip');
    expect(sent?.init?.method).toBe('POST');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ assignments: { bhdmz: 'a' } });
    view.unmount();
    renderAt('/settings?tab=templates');
    const one = await screen.findByRole('button', { name: 'Download BH-DMZ switch (2930F, OOBM port 2)' });
    expect(one).toBeDisabled(); // needs a zone first
    await userEvent.type(screen.getByLabelText('Download for zone'), '7');
    await userEvent.click(one);
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/templates/bhdmz/file?zone=7')).toBe(true));
    await userEvent.click(screen.getByRole('button', { name: 'All files for zone 7' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/templates/files.zip?zone=7')).toBe(true));
  });
});

describe('Nokia modem: first access over the console (D-112)', () => {
  const modem = (over: Partial<Device> = {}) => device({ id: 'm1', name: 'lab-modem', manufacturer: 'Nokia', model: '7705 SAR-Hmc',
    category: 'router', role: 'Nokia 7705 SAR-Hmc (modem)', driver_id: 'mock.nokia.sar', management_address: '',
    credential_ref_id: 'approved', ...over });
  const driver = { driver_id: 'mock.nokia.sar', platform: 'sros_sar', simulated: true, vendor: 'Nokia', os_family: 'SR OS (7705 SAR)',
    description: '', capabilities: [], maturity: 'simulation', transport: 'simulated', notes: [] };
  const preview = { supported: true, procedure: 'first_access', commands: ['Enter, within 3 seconds of its question', 'sros (it counts down from 30 seconds)', 'bof save'],
    notes: ['Console speed 115200.'] };

  it('Console setup shows the steps and runs the first access after the typed name', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({
      '/devices': [modem()], '/drivers': [driver], '/projects/p1/credential-refs': [{ id: 'approved', name: 'approved', shared: true }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated console', hardware_id: '' }],
      '/devices/m1/provisioning/console-bootstrap/preview': preview,
      '/devices/m1/provisioning/console-bootstrap': { status: 'bootstrapped', message: 'First access done on NS00SIM0001.', commands_sent: [],
        findings: [], verified: true, saved: true, transcript: 'Login: admin', sanitized_transcript: 'Login: admin', password_set: true,
        network_reachable: null, network_hint: 'Next: its configuration.', facts: { type: '7705 SAR-Hmc', version: 'B-20.5.R1' },
        diagnostics: { at_question: 'Hit a key within 3 seconds to change boot parameters...\\b\\b\\b', control_characters_ignored: '\\b ×3' } },
    });
    renderAt('/console?device=m1');
    expect(await screen.findByText(/sros \(it counts down from 30 seconds\)/)).toBeInTheDocument();
    // No VLAN or address to enter: that is the 2930F's console setup.
    expect(screen.queryByLabelText(/Untagged port/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Run first access…' }));
    const go = await screen.findByRole('button', { name: 'Run first access' });
    expect(go).toBeDisabled();
    expect(screen.getByText(/Then switch the modem off and on/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Type the device name to confirm/), 'lab-modem');
    await userEvent.click(go);
    expect(await screen.findByText('First access done')).toBeInTheDocument();
    const sent = calls.find((c) => c.url === '/api/devices/m1/provisioning/console-bootstrap' && c.init?.method === 'POST');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ serial_port: 'SIMULATED', baudrate: 115200, confirm_device_name: 'lab-modem', allow_configured: false });
    expect(screen.getByText('admin password set')).toBeInTheDocument();
    expect(screen.getByText('7705 SAR-Hmc · B-20.5.R1')).toBeInTheDocument();
    expect(screen.getByText(/Technical details: what the console sent around the question/)).toBeInTheDocument();
  });

  it('while the first access runs, it shows what UNDM sees on the console', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({
      '/devices': [modem()], '/drivers': [driver], '/projects/p1/credential-refs': [{ id: 'approved', name: 'approved', shared: true }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated console', hardware_id: '' }],
      '/devices/m1/provisioning/console-bootstrap/preview': preview,
      '/devices/m1/provisioning/console-progress': { running: true, stage: 'listening', seconds: 100, received: 23456, last_line: '[   21.5] Run /sbin/init' },
    });
    const answered = globalThis.fetch;
    // The run itself never answers in this test: the page stays on "working".
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => (url === '/api/devices/m1/provisioning/console-bootstrap' && init?.method === 'POST'
      ? new Promise(() => {}) : answered(url, init))));
    renderAt('/console?device=m1');
    await userEvent.click(await screen.findByRole('button', { name: 'Run first access…' }));
    expect(await screen.findByText(/About 2½ minutes later it asks for a key for 3 seconds/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Type the device name to confirm/), 'lab-modem');
    await userEvent.click(screen.getByRole('button', { name: 'Run first access' }));
    expect(await screen.findByText(/its start-up text is arriving/)).toBeInTheDocument();
    expect(screen.getByText(/1 min 40 s · 23,456 bytes received/)).toBeInTheDocument();
    expect(screen.getByText(/21\.5\] Run \/sbin\/init/)).toBeInTheDocument();
  });

  it('a login the modem cannot take blocks the run with the reason', async () => {
    mockApi({
      '/devices': [modem()], '/drivers': [driver], '/projects/p1/credential-refs': [],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated console', hardware_id: '' }],
      '/devices/m1/provisioning/console-bootstrap/preview': { ...preview, notes: ["Before you run: The modem's administrator is 'admin': choose a login with that user name."] },
    });
    renderAt('/console?device=m1');
    expect(await screen.findByText(/The modem's administrator is 'admin'/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run first access…' })).toBeDisabled();
  });

  it('the wizard stages the modem: its first access, then its file over the console by a plan (D-116)', async () => {
    const project = { id: 'p1', name: 'Lab z045', description: '', site: '', purpose: '', created_at: '', updated_at: '',
      certificate_subject: null, staged_at: null, staged_by: '', zone: 45 };
    const policy = { enable_real_device_writes: false, enable_real_device_firmware: false, firmware_require_separate_approver: false, locked: [] };
    const real = (over: Partial<Device>) => modem({ driver_id: 'console.nokia.sar', environment: 'lab', ...over });
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [real({ provisioning_status: 'planned' })], '/projects/p1/staging-plans': [], '/policy': policy });
    const first = renderAt('/stage/p1?step=3');
    expect(await screen.findByText('1. First access (console)')).toBeInTheDocument();
    expect(screen.getByText('2. Its configuration file (console)')).toBeInTheDocument();
    // D-121: its first access opens inside the wizard, and returns to this step.
    expect(screen.getByRole('link', { name: 'Open console setup' })).toHaveAttribute('href', '/stage/p1?step=3&console=m1');
    expect(screen.getByText(/Do its first access first/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check and run…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Check and run…' })).toHaveAccessibleDescription('Its first access comes first.');
    first.unmount();
    const bench = renderAt('/stage/p1?step=2');
    expect(await screen.findByText('After its first access (it saves the console port)')).toBeInTheDocument();
    expect(screen.getByText(/Nokia modem: its console cable only, at speed 115200/)).toBeInTheDocument();
    bench.unmount();
    // After its first access: the console port it saved, and its file to choose; not staged yet.
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [real({ provisioning_status: 'bootstrapped', console_port: 'COM7' })],
      '/projects/p1/staging-plans': [], '/policy': policy });
    const run = renderAt('/stage/p1?step=3');
    expect(await screen.findByText(/console COM7/)).toBeInTheDocument();
    expect(screen.getByText(/Still needed: the team file/)).toBeInTheDocument();
    expect(screen.getByText(/the load stops, unsaved, at the first line the modem refuses/)).toBeInTheDocument();
    run.unmount();
    const files = renderAt('/stage/p1?step=1');
    expect(await screen.findByText('Configuration file')).toBeInTheDocument();
    expect(screen.queryByText(/Login after loading/)).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Firmware' })).not.toBeInTheDocument();
    files.unmount();
    renderAt('/stage/p1?step=4');
    expect((await screen.findAllByText(/Still to do in step 4 \(Run\)/)).length).toBeGreaterThan(0);
    // D-121: each device still to do links to its card in step 4.
    expect(screen.getByRole('link', { name: 'lab-modem' })).toHaveAttribute('href', '/stage/p1?step=3#device-m1');
  });
});

describe('the Flexi BBU: staged by hand in its portal, guided and recorded (D-117)', () => {
  const project = { id: 'p1', name: 'Lab z045', description: '', site: '', purpose: '', created_at: '', updated_at: '',
    certificate_subject: null, staged_at: null, staged_by: '', zone: 45, system_id: 'B007' };
  const bbu = device({ id: 'b1', name: 'lab-bbu', manufacturer: 'Nokia', model: 'FSMF', category: 'other',
    role: 'Nokia Flexi BBU (FSMF)', driver_id: 'guided.nokia.flexi', management_address: '192.0.2.129', credential_ref_id: null, environment: 'lab',
    capabilities: ['supports_guided_staging'] });
  const step = (key: string, title: string, kind: string, over: Record<string, unknown> = {}) => ({ key, title, detail: `${title} detail`, kind,
    note_label: kind === 'check' ? '' : 'What you saw', done_by: null, done_at: null, note: '', file_name: null, file_sha256: null, ...over });
  const guided = (done: number) => ({ procedure: 'flexi_bbu', title: 'Flexi BBU', steps: [
    step('portal', 'Its portal answers', 'check'), step('software', 'Software package loaded and in use', 'software'),
    step('scf', 'Site configuration file (SCF) loaded and in use', 'file'), step('state', 'Its state checked', 'manual'),
  ].map((s, i) => (i < done ? { ...s, done_by: 'tester', done_at: '2026-01-01T10:00:00Z', note: 'ok',
    ...(s.kind === 'software' ? { file_name: 'SBTS_EXAMPLE.zip', file_sha256: 'ab'.repeat(32) } : {}) } : s)) });
  const image = { id: 'img1', vendor: 'Nokia', platform: 'flexi_sbts', version: 'SBTS-EXAMPLE', filename: 'SBTS_EXAMPLE.zip',
    size_bytes: 10, sha256: 'ab'.repeat(32), vendor_sha256: null, status: 'approved', compatible_models: ['FSMF'] };
  const scf = { id: 'v1', device_id: 'b1', kind: 'imported', sha256: 'x', platform: 'flexi_sbts', template_version: 'v1',
    verification: 'generated_from_team_template', reference: 'Full_scf_MRBTS-7_x.xml', created_by: 't', created_at: '' };

  it('the run board guides each step and records it; no login, no plan', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    window.localStorage.setItem('undm.stage.p1', JSON.stringify({ bbu: { firstLogin: false, imageId: 'img1', allowDowngrade: false,
      alsoSecondary: false, baseId: null, siteId: null, fileId: 'v1', loginAfter: null, secrets: {} } }));
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [bbu], '/projects/p1/staging-plans': [],
      '/devices/b1/guided': guided(1), '/firmware/images': [image], '/devices/b1/configs': [scf], '/devices/b1/guided/software': guided(2) });
    const first = renderAt('/stage/p1?step=0');
    expect(await screen.findByText(/No login in UNDM: UNDM never logs in to the BBU/)).toBeInTheDocument();
    first.unmount();
    renderAt('/stage/p1?step=3');
    expect(await screen.findByText('2. Software package loaded and in use')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open its portal' })).toHaveAttribute('href', 'https://192.0.2.129');
    expect(await screen.findByText('SBTS_EXAMPLE.zip · SBTS-EXAMPLE')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Download it from UNDM/ })).toHaveAttribute('href', '/api/firmware/images/img1/file');
    expect(screen.queryByRole('button', { name: 'Check and run…' })).not.toBeInTheDocument();
    const doneButton = screen.getByRole('button', { name: 'Done' });
    expect(doneButton).toBeDisabled();  // what the person saw is noted first
    await userEvent.type(screen.getByLabelText('What you saw'), 'Software page; shows SBTS-EXAMPLE');
    await userEvent.click(doneButton);
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/devices/b1/guided/software' && c.init?.method === 'POST')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/devices/b1/guided/software');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ note: 'Software page; shows SBTS-EXAMPLE', image_id: 'img1', version_id: 'v1' });
    window.localStorage.removeItem('undm.stage.p1');
  });

  it('the report lists the steps, and the BBU counts as staged once all are recorded', async () => {
    mockApi({ '/projects/p1': project, '/projects/p1/devices': [bbu], '/projects/p1/staging-plans': [], '/devices/b1/guided': guided(4),
      '/policy': { enable_real_device_writes: false, enable_real_device_firmware: false, firmware_require_separate_approver: false, locked: [] } });
    renderAt('/stage/p1?step=4');
    const table = await screen.findByRole('table', { name: 'Steps done in the portal of lab-bbu' });
    await vi.waitFor(() => expect(table.textContent).toContain('SBTS_EXAMPLE.zip · SHA-256 ' + 'ab'.repeat(32)));
    expect(screen.queryByText(/Still to do in step 4/)).not.toBeInTheDocument();
  });
});

describe('the modem and the BBU: files by zone and system (D-114)', () => {
  const project = (over: Record<string, unknown> = {}) => ({ id: 'p1', name: 'Lab B7z045', description: '', site: '', purpose: '',
    created_at: '', updated_at: '', certificate_subject: null, staged_at: null, staged_by: '', zone: null, system_id: null, ...over });
  const tpl = (role: string, over: Record<string, unknown> = {}) => ({ id: `t-${role}`, role, version: 'v1', filename: 'x', reference_zone: 41,
    reference_system: 'B007', counts: {}, verified_zone: 42, verified_system: 'B009', line_ending: 'lf', final_newline: true,
    created_by: 't', created_at: '', older: 0, ...over });

  it('the system starts from the system name, is saved with the zone and shows its PCIs', async () => {
    const calls = mockApi({ '/projects/p1': project(), '/projects/p1/devices': [], '/projects/p1/staging-plans': [],
      '/settings/pci-mapping/B007': { system: 'B007', pcis: [12, 13] } });
    renderAt('/stage/p1?step=0');
    expect(await screen.findByDisplayValue('B007')).toBeInTheDocument();
    expect(await screen.findByText(/MRBTS-7 · cell PCIs 12, 13 \(PCI table\)/)).toBeInTheDocument();
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/projects/p1' && c.init?.method === 'PATCH')).toBe(true));
    const sent = calls.find((c) => c.url === '/api/projects/p1' && c.init?.method === 'PATCH');
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ zone: 45, system_id: 'B007' });
  });

  it('the wizard asks for the system before files that depend on it, and says what the download left out', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
    const modemDevice = device({ id: 'm', name: 'lab-modem', manufacturer: 'Nokia', model: '7705 SAR-Hmc', category: 'router',
      role: 'Nokia 7705 SAR-Hmc (modem)', driver_id: 'mock.nokia.sar', management_address: '' });
    mockApi({ '/projects/p1': project({ zone: 45 }), '/projects/p1/staging-plans': [], '/projects/p1/devices': [modemDevice],
      '/templates': [tpl('modem'), tpl('bbu_scf')] });
    const first = renderAt('/stage/p1?step=1');
    expect(await screen.findByText(/Set the system \(e\.g\. B007\) in step 1 first/)).toBeInTheDocument();
    first.unmount();
    const calls = mockApi({ '/projects/p1': project({ zone: 45, system_id: 'B007' }), '/projects/p1/staging-plans': [],
      '/projects/p1/devices': [modemDevice], '/templates': [tpl('modem'), tpl('bbu_scf')] });
    const answered = globalThis.fetch;
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => (url === '/api/projects/p1/files.zip'
      ? Promise.resolve(new Response('zip', { status: 200, headers: { 'Content-Disposition': 'attachment; filename="B007-files.zip"',
        'X-UNDM-Skipped': encodeURIComponent(JSON.stringify(["LTE modem configuration: choose the modem's login first (step 1)"])) } }))
      : answered(url, init))));
    renderAt('/stage/p1?step=1');
    await userEvent.click(await screen.findByRole('button', { name: 'Download the files for zone 45 · B007' }));
    expect(await screen.findByText(/choose the modem's login first/)).toBeInTheDocument();
    expect(screen.getByText(/It includes the Flexi BBU’s SCF/)).toBeInTheDocument();
    expect(calls.length).toBeGreaterThan(0);
  });

  it('an import whose second file differs shows the lines and can be kept anyway', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/templates': [], '/credential-refs': [], '/settings/certificate': { subject: null }, '/settings/pci-mapping': null });
    const answered = globalThis.fetch;
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/templates' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as { accept_differences?: boolean };
        bodies.push(body);
        return Promise.resolve(body.accept_differences
          ? new Response(JSON.stringify({ template: tpl('bbu_scf', { counts: { accepted_differences: 1 } }), to_check: [], verified_bytes: false,
            accepted: ["line 4: UNDM 'label A' / file 'label B'"] }), { status: 201, headers: { 'Content-Type': 'application/json' } })
          : new Response(JSON.stringify({ error: 'The template does not give the zone 42, system B009 file exactly: 1 line(s) differ, first at line 4. Nothing was kept.',
            details: ["line 4: UNDM 'label A' / file 'label B'"] }), { status: 409, headers: { 'Content-Type': 'application/json' } }));
      }
      return answered(url, init);
    }));
    renderAt('/settings?tab=templates');
    const row = (await screen.findByText('Flexi BBU site configuration file (SCF)')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Import…' }));
    const dialog = await screen.findByRole('dialog');
    // Mantine's file inputs: a button with a hidden <input type=file> (the team's file, then the second file).
    await userEvent.upload(dialog.querySelectorAll('input[type="file"]')[0] as HTMLInputElement, new File(['<raml/>'], 'scf_MRBTS-7_x-Z041.xml'));
    await userEvent.upload(dialog.querySelectorAll('input[type="file"]')[1] as HTMLInputElement, new File(['<raml/>'], 'scf_MRBTS-9_x-Z042.xml'));
    await vi.waitFor(() => expect(within(dialog).getByLabelText('Its system')).toHaveValue('B009')); // from MRBTS-9 in its name
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    expect(await within(dialog).findByText("line 4: UNDM 'label A' / file 'label B'")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep it anyway' }));
    expect(await within(dialog).findByText(/except 1 accepted line/)).toBeInTheDocument();
    expect(bodies).toHaveLength(2);
    expect((bodies[1] as { accept_differences?: boolean; verify?: { system?: string } }).accept_differences).toBe(true);
    expect((bodies[1] as { verify?: { system?: string } }).verify?.system).toBe('B009');
  });

  it('the import reads the zone and the system from the file name, else from its text', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const { systemInName, zoneInName } = await import('../src/features/stage/zone');
    // Names as the team writes them (bench, 2026-11-26): zone without leading zeros; eNB1 is not a system.
    expect(zoneInName('LTEModemz41.txt')).toBe(41);
    expect(zoneInName('B007z045')).toBe(45);
    expect(zoneInName('z41-z42.txt')).toBeUndefined();
    expect(systemInName('Full_Configuration_scf_MRBTS-7_eNB1-ABCB-007-Z041_20260101-1200.xml')).toBe('B007');
    expect(systemInName('lab b7 zone')).toBe('B007');
    expect(systemInName('eNB1.xml')).toBeUndefined();
    const bodies: Record<string, unknown>[] = [];
    mockApi({ '/templates': [], '/credential-refs': [], '/settings/certificate': { subject: null }, '/settings/pci-mapping': null });
    const answered = globalThis.fetch;
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/templates' && init?.method === 'POST') {
        bodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Promise.resolve(new Response(JSON.stringify({ template: tpl('modem'), to_check: [], verified_bytes: null, accepted: [] }),
          { status: 201, headers: { 'Content-Type': 'application/json' } }));
      }
      return answered(url, init);
    }));
    renderAt('/settings?tab=templates');
    const row = (await screen.findByText('LTE modem (Nokia 7705 SAR-Hmc)')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Import…' }));
    const dialog = await screen.findByRole('dialog');
    const files = () => dialog.querySelectorAll('input[type="file"]');
    await userEvent.upload(files()[0] as HTMLInputElement,
      new File(['configure\n  system\n    name "LTEmodemABCB007"\n  exit\n'], 'LTEModemz41.txt'));
    await vi.waitFor(() => expect(within(dialog).getByLabelText('Zone of this file')).toHaveValue('41'));
    expect(within(dialog).getByLabelText('System of this file')).toHaveValue('B007');
    expect(within(dialog).getByText('Read from its name.')).toBeInTheDocument();
    expect(within(dialog).getByText('Read from the file (its name does not say).')).toBeInTheDocument();
    // A second file whose name and text disagree is pointed out.
    await userEvent.upload(files()[1] as HTMLInputElement, new File(['name "LTEmodemABCB009-Zone043"'], 'LTEModemz42.txt'));
    expect(await within(dialog).findByText('Check this file: its name says zone 42, its text zone 43.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Its system')).toHaveValue('B009');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    await vi.waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ role: 'modem', filename: 'LTEModemz41.txt', zone: 41, system: 'B007',
      verify: { filename: 'LTEModemz42.txt', zone: 42, system: 'B009' } });
  });

  it('a zone typed by the person is kept when a file is chosen', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    mockApi({ '/templates': [], '/credential-refs': [], '/settings/certificate': { subject: null }, '/settings/pci-mapping': null });
    renderAt('/settings?tab=templates');
    const row = (await screen.findByText('Flexi BBU site configuration file (SCF)')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Import…' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Zone of this file'), '45');
    await userEvent.upload(dialog.querySelectorAll('input[type="file"]')[0] as HTMLInputElement,
      new File(['<raml/>'], 'Full_Configuration_scf_MRBTS-7_eNB1-ABCB-007-Z041_20260101-1200.xml'));
    await vi.waitFor(() => expect(within(dialog).getByLabelText('System of this file')).toHaveValue('B007'));
    expect(within(dialog).getByLabelText('Zone of this file')).toHaveValue('45');
  });

  it('the PCI table is imported once and looked up by system', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/templates': [], '/credential-refs': [], '/settings/certificate': { subject: null },
      '/settings/pci-mapping': { filename: 'pci.xlsx', sha256: 'x', imported_at: null, imported_by: 'tester', systems: 3, cells: 2 },
      '/settings/pci-mapping/B007': { system: 'B007', pcis: [12, 13] } });
    renderAt('/settings?tab=templates');
    expect(await screen.findByText('3 systems')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Look up a system'), 'b7');
    expect(await screen.findByText('B007: 12, 13')).toBeInTheDocument();
    const input = document.querySelector('input[type="file"][accept=".xlsx,.csv,text/csv"]') as HTMLInputElement;
    await userEvent.upload(input, new File(['x'], 'pci.xlsx'));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/pci-mapping' && c.init?.method === 'POST')).toBe(true));
  });
});

describe('Stage a system, steps 1 to 3 (D-121)', () => {
  const project = { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '',
    certificate_subject: null, staged_at: null, staged_by: '', zone: 41, system_id: null };
  const model = (model_id: string, manufacturer: string, name: string, category = 'switch') =>
    ({ model_id, manufacturer, product_family: '', model: name, category, os_family: '', drivers: [], support: '', notes: '' });

  it('adds every missing device at once, with the same defaults as each card', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [], '/projects/p1/staging-plans': [],
      '/device-models': [model('fortinet-fg-101f', 'Fortinet', 'FortiGate-101F', 'firewall'), model('blackbox-lig1014a', 'Black Box', 'LIG1014A')] });
    renderAt('/stage/p1?step=0');
    await userEvent.click(await screen.findByRole('radio', { name: 'Practice (simulated)' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Add all missing devices (2)' }));
    await vi.waitFor(() => expect(calls.filter((c) => c.url === '/api/projects/p1/devices' && c.init?.method === 'POST')).toHaveLength(2));
    const bodies = calls.filter((c) => c.url === '/api/projects/p1/devices' && c.init?.method === 'POST').map((c) => JSON.parse(String(c.init?.body)));
    expect(bodies.map((b) => [b.name, b.environment, b.role])).toEqual([
      ['lab-a-fw', 'simulated', 'FortiGate 101F'], ['lab-a-bb', 'simulated', 'Black Box LIG1014A']]);
    // Real or practice is remembered for this system.
    expect(JSON.parse(window.localStorage.getItem('undm.wizard.p1') ?? '{}').mode).toBe('simulated');
  });

  it('Test all checks every device that can be tested; a real 2930F waits for its console setup', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/staging-plans': [], '/projects/p1/devices': [
      device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A', driver_id: 'mock.blackbox.switch', management_address: '192.0.2.1' }),
      device({ id: 'fw', name: 'lab-a-fw', manufacturer: 'Fortinet', model: 'FortiGate-101F', driver_id: 'mock.fortinet.fortios', management_address: '192.168.1.99' }),
      device({ id: 'sa', name: 'lab-a-sw-a', manufacturer: 'Aruba', model: '2930F', driver_id: 'ssh.aruba.aos_switch', environment: 'lab',
        management_address: '192.168.1.1', provisioning_status: 'planned', credential_ref_id: 'c1' }),
    ], '/devices/bb/operations/check_reachability': { status: 'success', message: 'ok' },
    '/devices/fw/operations/check_reachability': { status: 'success', message: 'ok' } });
    renderAt('/stage/p1?step=2');
    expect(await screen.findByText('After its console setup (it then answers at its address)')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Test all (2)' }));
    await vi.waitFor(() => expect(screen.getAllByText('Connected')).toHaveLength(2));
    const tested = calls.filter((c) => c.url.endsWith('/operations/check_reachability')).map((c) => c.url);
    // In the order of the roles, one after the other.
    expect(tested).toEqual(['/api/devices/fw/operations/check_reachability', '/api/devices/bb/operations/check_reachability']);
    // Its console setup opens inside the wizard, and comes back to this step.
    expect(screen.getByRole('link', { name: 'Open console setup' })).toHaveAttribute('href', '/stage/p1?step=2&console=sa');
  });

  it('console setup inside the wizard keeps the steps and returns to the step it came from', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const sw = device({ id: 'sa', name: 'lab-a-sw-a', manufacturer: 'Aruba', model: '2930F', driver_id: 'mock.aruba.aos_switch', management_address: '192.168.1.1' });
    mockApi({ '/projects/p1': project, '/projects/p1/staging-plans': [], '/projects/p1/devices': [sw],
      '/drivers': [{ driver_id: 'mock.aruba.aos_switch', platform: 'aos_switch', simulated: true, capabilities: [], description: '', vendor: 'Aruba', os_family: '', maturity: 'simulated' }],
      '/provisioning/serial-ports': [{ port: 'SIMULATED', description: 'Simulated switch console', hardware_id: '' }] });
    const view = renderAt('/stage/p1?step=2&console=sa');
    expect(await screen.findByRole('heading', { name: 'lab-a-sw-a: console' })).toBeInTheDocument();
    expect(screen.getByText('Bench check')).toBeInTheDocument();  // the stepper stays
    expect(await screen.findByRole('button', { name: 'Preview commands' })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: 'Back to Bench check' })[0]);
    await vi.waitFor(() => expect(view.here()).toBe('/stage/p1?step=2'));
  });

  it('the only approved image that fits a real device is chosen once; clearing it keeps it cleared', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    window.localStorage.removeItem('undm.stage.p1');
    const image = { id: 'img1', vendor: 'Black Box', platform: 'blackbox', version: 'v00.01.01', filename: 'lig.bin', size_bytes: 10,
      sha256: 'ab'.repeat(32), vendor_sha256: null, status: 'approved', compatible_models: ['LIG1014A'] };
    mockApi({ '/projects/p1': project, '/projects/p1/staging-plans': [], '/firmware/images': [image], '/projects/p1/devices': [
      device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A', driver_id: 'ssh.blackbox.lig1014a', environment: 'lab',
        management_address: '192.0.2.1', credential_ref_id: 'c1' })] });
    const view = renderAt('/stage/p1?step=1');
    expect(await screen.findByDisplayValue('v00.01.01 · lig.bin')).toBeInTheDocument();
    await vi.waitFor(() => expect(JSON.parse(window.localStorage.getItem('undm.stage.p1') ?? '{}').blackbox?.imageId).toBe('img1'));
    const field = screen.getByDisplayValue('v00.01.01 · lig.bin');
    await userEvent.click(field.parentElement!.querySelector('button')!);  // the clear button
    await vi.waitFor(() => expect(JSON.parse(window.localStorage.getItem('undm.stage.p1') ?? '{}').blackbox?.imageId).toBeNull());
    view.unmount();
    renderAt('/stage/p1?step=1');
    expect(await screen.findByText('lab-a-bb', { exact: false })).toBeInTheDocument();
    expect(screen.queryByDisplayValue('v00.01.01 · lig.bin')).not.toBeInTheDocument();
    window.localStorage.removeItem('undm.stage.p1');
  });

  it('Settings has a default login for the modem', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const calls = mockApi({ '/credential-refs': [{ id: 'ok', name: 'approved', provider: 'keyring', locator: 'credential/ok', has_secret: true, shared: true }],
      '/settings/defaults': { firewall: { login: null, login_after: null, tunnel_key: null }, blackbox: { login: null, login_after: null },
        aruba: { login: null, current: null } } });  // as stored before v94: no modem row
    renderAt('/settings?tab=logins');
    expect(await screen.findByRole('heading', { name: 'Nokia 7705 SAR-Hmc (modem)' })).toBeInTheDocument();
    // The form starts again once the stored defaults have arrived: wait for that.
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/defaults')).toBe(true));
    await new Promise((r) => setTimeout(r, 50));
    await userEvent.click(await screen.findByRole('button', { name: 'Save default logins' }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/settings/defaults' && c.init?.method === 'PUT')).toBe(true));
    const put = calls.find((c) => c.url === '/api/settings/defaults' && c.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body)).modem).toEqual({ login: null });
  });
});

describe('Stage a system, run and report (D-121)', () => {
  const project = { id: 'p1', name: 'Lab A', description: '', site: '', purpose: '', created_at: '', updated_at: '',
    certificate_subject: null, staged_at: null, staged_by: '', zone: 41, system_id: null };
  const sw = device({ id: 'sa', name: 'lab-a-sw-a', manufacturer: 'Aruba', model: '2930F', driver_id: 'mock.aruba.aos_switch',
    management_address: '192.168.1.1', provisioning_status: 'bootstrapped', role: 'Aruba 2930F (OOBM port 2)' });
  const bb = device({ id: 'bb', name: 'lab-a-bb', manufacturer: 'Black Box', model: 'LIG1014A', driver_id: 'mock.blackbox.switch',
    management_address: '192.0.2.1' });
  const pol = { enable_real_device_writes: false, enable_real_device_firmware: false, allow_production_read_only: false,
    allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: true, locked: [] };
  const step = (n: number, kind: string, state = 'awaiting_approval') => ({ id: `st${n}`, project_id: 'p1', kind, state, dry_run: false,
    apply_mode: 'replace', created_by: 'local-user', approved_by: null, created_at: '', updated_at: '', staging_id: 'sp9', staging_step: n,
    targets: [{ device_id: 'sa', position: 0, config_version_id: null, backup_version_id: null, state: 'previewed', diff: '', message: '' }],
    events: [], firmware_image_id: null, window_start: null, window_end: null, approved_at: null });

  it('Check and run: staging alone switches the second-approver rule off for this approval only', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    window.localStorage.setItem('undm.stage.p1', JSON.stringify({ aruba_a: { ...{ firstLogin: false, imageId: 'img1', allowDowngrade: false,
      alsoSecondary: false, baseId: null, siteId: null, fileId: 'v1', loginAfter: null, secrets: {} } } }));
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [sw], '/projects/p1/staging-plans': [], '/policy': pol,
      '/devices/sa': sw, '/projects/p1/device-staging': { staging_id: 'sp9', steps: [step(1, 'firmware'), step(2, 'configuration')] } });
    renderAt('/stage/p1?step=3');
    await userEvent.click(await screen.findByRole('button', { name: 'Check and run…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Check and run: lab-a-sw-a' });
    const go = await within(dialog).findByRole('button', { name: 'Approve and run' });
    expect(go).toBeDisabled();
    expect(go).toHaveAccessibleDescription('Tick “I am staging alone”, or let a second person approve it.');
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'I am staging alone' }));
    await userEvent.click(go);
    await vi.waitFor(() => expect(calls.some((c) => c.url === '/api/staging-plans/sp9/execute?background=true')).toBe(true));
    const seen = calls.filter((c) => c.init?.method === 'PUT' || c.init?.method === 'POST')
      .map((c) => `${c.init?.method} ${c.url.replace(/\?.*$/, '')} ${c.url.includes('/policy') ? String(c.init?.body) : ''}`.trim());
    expect(seen).toEqual([
      'POST /api/projects/p1/device-staging',
      'PUT /api/policy {"firmware_require_separate_approver":false}',
      'POST /api/staging-plans/sp9/approve',
      'PUT /api/policy {"firmware_require_separate_approver":true}',
      'POST /api/staging-plans/sp9/execute',
    ]);
    const approve = calls.find((c) => c.url === '/api/staging-plans/sp9/approve');
    expect(Object.keys(JSON.parse(String(approve?.init?.body)))).toEqual(['window_start', 'window_end']);
    window.localStorage.removeItem('undm.stage.p1');
  });

  it('Start all ready makes, approves and runs a plan per ready device, and says who waits', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const swB = device({ id: 'sb', name: 'lab-a-sw-b', manufacturer: 'Aruba', model: '2930F', driver_id: 'mock.aruba.aos_switch',
      management_address: '192.168.1.2', provisioning_status: 'bootstrapped', role: 'Aruba 2930F (OOBM port 3)' });
    const file = { firstLogin: false, imageId: null, allowDowngrade: false, alsoSecondary: false, baseId: null, siteId: null, fileId: 'v1', loginAfter: null, secrets: {} };
    window.localStorage.setItem('undm.stage.p1', JSON.stringify({ blackbox: file, aruba_a: file, aruba_b: file }));
    const calls = mockApi({ '/projects/p1': project, '/projects/p1/devices': [bb, sw, swB], '/projects/p1/staging-plans': [], '/policy': pol,
      '/projects/p1/device-staging': { staging_id: 'sp9', steps: [step(1, 'configuration')] } });
    renderAt('/stage/p1?step=3');
    await userEvent.click(await screen.findByRole('button', { name: 'Start all ready (2)…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Start all ready devices' });
    expect(within(dialog).getByText('lab-a-sw-b: it starts once lab-a-sw-a is staged (same final address)')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Start 2 devices' }));
    expect(await within(dialog).findByText('lab-a-bb: started')).toBeInTheDocument();
    expect(within(dialog).getByText('lab-a-sw-a: started')).toBeInTheDocument();
    const posts = calls.filter((c) => c.init?.method === 'POST').map((c) => c.url.replace(/\?.*$/, ''));
    expect(posts.filter((u) => u.endsWith('/device-staging'))).toHaveLength(2);
    expect(posts.filter((u) => u.endsWith('/approve'))).toHaveLength(2);
    expect(posts.filter((u) => u.endsWith('/execute'))).toHaveLength(2);
    expect(calls.some((c) => c.url === '/api/policy' && c.init?.method === 'PUT')).toBe(false);  // no firmware: no rule changed
    window.localStorage.removeItem('undm.stage.p1');
  });
});

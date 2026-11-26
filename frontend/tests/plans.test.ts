import { afterEach, describe, expect, it, vi } from 'vitest';

import { approveAlone, needsSecondPerson, soloOffered } from '../src/features/plans/soloApproval';
import { defaultWindow, windowProblem } from '../src/features/plans/window';
import { EMPTY_CHOICE } from '../src/features/stage/choices';
import { ROLES } from '../src/features/stage/roles';
import { failureReason } from '../src/features/stage/staging';
import { startOrder } from '../src/features/stage/startOrder';
import { api } from '../src/services/api';
import type { Deployment, Device, Policy, StagingIndex } from '../src/types/api';

const policy = (over: Partial<Policy> = {}): Policy => ({
  enable_real_device_writes: true, enable_real_device_firmware: true, allow_production_read_only: false,
  allow_production_deployments: false, require_separate_approver: false, firmware_require_separate_approver: true, locked: [], ...over });

afterEach(() => vi.restoreAllMocks());

describe('the approval window (D-121)', () => {
  it('runs from five minutes ago to eight hours ahead, in UTC', () => {
    const now = Date.parse('2026-11-26T10:00:00Z');
    expect(defaultWindow(now)).toEqual({ start: '2026-11-26T09:55', end: '2026-11-26T18:00' });
  });
  it('refuses an empty, reversed or too long window', () => {
    expect(windowProblem({ start: '', end: '2026-11-26T18:00' })).toBe('Give both times.');
    expect(windowProblem({ start: '2026-11-26T18:00', end: '2026-11-26T10:00' })).toBe('The end must be after the start.');
    expect(windowProblem({ start: '2026-11-26T00:00', end: '2026-11-27T00:01' })).toBe('At most 24 hours.');
    expect(windowProblem({ start: '2026-11-26T09:55', end: '2026-11-26T18:00' })).toBeNull();
  });
});

describe('staging alone (D-121)', () => {
  const who = { firmware: true, maker: 'alex', actor: 'alex' };
  it('is offered only to the maker of a firmware plan while the rule is on and not fixed', () => {
    expect(soloOffered(policy(), who)).toBe(true);
    expect(soloOffered(policy(), { ...who, firmware: false })).toBe(false);
    expect(soloOffered(policy(), { ...who, actor: 'sam' })).toBe(false);  // sam is the second person
    expect(soloOffered(policy({ firmware_require_separate_approver: false }), who)).toBe(false);
    expect(soloOffered(policy({ locked: ['firmware_require_separate_approver'] }), who)).toBe(false);
    expect(needsSecondPerson(policy({ locked: ['firmware_require_separate_approver'] }), who)).toBe(true);
  });

  it('switches the rule off for the approval and on again at once, also when the approval fails', async () => {
    const order: string[] = [];
    vi.spyOn(api, 'changePolicy').mockImplementation(async (c) => { order.push(`rule ${String(c.firmware_require_separate_approver)}`); return policy(); });
    expect(await approveAlone(async () => { order.push('approve'); return 'ok'; })).toBe('ok');
    expect(order).toEqual(['rule false', 'approve', 'rule true']);
    order.length = 0;
    await expect(approveAlone(async () => { order.push('approve'); throw new Error('outside the window'); })).rejects.toThrow('outside the window');
    expect(order).toEqual(['rule false', 'approve', 'rule true']);
  });

  it('says so when the rule cannot be switched back on', async () => {
    vi.spyOn(api, 'changePolicy').mockImplementation(async (c) => {
      if (c.firmware_require_separate_approver) throw new Error('UNDM is not answering');
      return policy();
    });
    await expect(approveAlone(async () => 'ok')).rejects.toThrow(/Approved, but the rule .* could not be switched back on \(UNDM is not answering\)/);
  });
});

describe('Start all ready (D-121)', () => {
  const role = (key: string) => ROLES.find((r) => r.key === key)!;
  const dev = (id: string, over: Partial<Device> = {}) => ({ id, name: id, environment: 'simulated', provisioning_status: 'bootstrapped',
    management_address: '', observed_facts: null, credential_ref_id: 'c1', capabilities: [], ...over } as unknown as Device);
  const a = dev('sw-a', { management_address: '192.168.1.1' });
  const b = dev('sw-b', { management_address: '192.168.1.2' });
  const fw = dev('fw', { management_address: '192.168.1.99' });
  const bbu = dev('bbu', { management_address: '192.168.255.129' });
  const roles = [{ role: role('firewall'), device: fw }, { role: role('aruba_a'), device: a }, { role: role('aruba_b'), device: b },
    { role: role('bbu'), device: bbu }];
  const choices = { firewall: { ...EMPTY_CHOICE, baseId: 'base', siteId: 'site' }, aruba_a: { ...EMPTY_CHOICE, fileId: 'fa' },
    aruba_b: { ...EMPTY_CHOICE, fileId: 'fb' } };
  const plan = (device: string, states: string[], kinds = states.map(() => 'configuration')): StagingIndex =>
    ({ staging_id: `sp-${device}`, device_id: device, created_at: '', kinds, states });

  it('starts the ready devices; switch B waits for A; the BBU is done by hand', () => {
    const order = startOrder(roles, choices, []);
    expect(order.map((i) => [i.device.id, i.ready])).toEqual([['fw', true], ['sw-a', true], ['sw-b', false]]);
    expect(order[2].reason).toBe('it starts once sw-a is staged (same final address)');
  });

  it('B starts once A is staged; a staged device is left out; an open plan is reused', () => {
    const order = startOrder(roles, choices, [plan('sw-a', ['succeeded']), plan('fw', ['ready', 'awaiting_approval'], ['configuration', 'firmware'])]);
    expect(order.map((i) => i.device.id)).toEqual(['fw', 'sw-b']);
    expect(order[0]).toMatchObject({ ready: true, stagingId: 'sp-fw', firmware: true });
    expect(order[1].ready).toBe(true);
    expect(order[1].stagingId).toBeUndefined();  // a new plan
  });

  it('waits for console work, missing choices and a plan that did not succeed', () => {
    const order = startOrder([{ role: role('aruba_a'), device: { ...a, provisioning_status: 'planned' } },
      { role: role('blackbox'), device: dev('bb') }, { role: role('firewall'), device: fw }],
    { aruba_a: choices.aruba_a, firewall: choices.firewall }, [plan('fw', ['succeeded', 'failed'])]);
    expect(order.map((i) => [i.device.id, i.ready, i.reason])).toEqual([
      ['sw-a', false, 'its console setup comes first'],
      ['bb', false, 'still needed: the team file'],
      ['fw', false, 'its last plan did not succeed: see its card'],
    ]);
  });
});

describe('why a staging plan stopped (D-121)', () => {
  const step = (n: number, state: string, over: Partial<Deployment> = {}) => ({ id: `s${n}`, staging_step: n, state, kind: 'configuration',
    events: [], targets: [], ...over } as unknown as Deployment);
  it('names the step and its last error', () => {
    const r = failureReason([step(1, 'succeeded'), step(2, 'failed', { events: [
      { seq: 1, timestamp: '', stage: 'apply', status: 'info', message: 'sending' },
      { seq: 2, timestamp: '', stage: 'apply', status: 'error', message: 'The switch refused line 12' }] as Deployment['events'] }), step(3, 'cancelled')]);
    expect(r).toMatchObject({ step: { id: 's2' }, text: 'The switch refused line 12' });
    expect(failureReason([step(1, 'succeeded')])).toBeNull();
  });
});

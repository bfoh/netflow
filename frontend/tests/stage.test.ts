import { describe, expect, it } from 'vitest';

import { EMPTY_CHOICE, planSteps } from '../src/features/stage/choices';
import { addressTakenBy, assignRoles, ROLES } from '../src/features/stage/roles';
import type { Device } from '../src/types/api';

const role = (key: string) => ROLES.find((r) => r.key === key)!;

describe('stage a system: steps per device', () => {
  it('a new FortiGate: first login, firmware, base with its login, then site with the tunnel key', () => {
    const { steps, missing } = planSteps(role('firewall'), {
      ...EMPTY_CHOICE, imageId: 'img', baseId: 'b', siteId: 's', loginAfter: 'base-login', secrets: { slot: 'key' } });
    expect(missing).toEqual([]);
    expect(steps).toEqual([
      { kind: 'first_login' },
      { kind: 'firmware', image_id: 'img', allow_downgrade: false, also_secondary: false },
      { kind: 'configuration', version_id: 'b', credential_after_ref_id: 'base-login' },
      { kind: 'configuration', version_id: 's', secrets: { slot: 'key' } },
    ]);
  });

  it('firmware can be left as it is; a missing file is named', () => {
    const { steps, missing } = planSteps(role('blackbox'), { ...EMPTY_CHOICE });
    expect(steps).toEqual([]);
    expect(missing).toEqual(['the team file']);
  });

  it('each device plays one role; names decide between the two 2930F', () => {
    const d = (id: string, name: string, model: string) => ({ id, name, model } as Device);
    const roles = assignRoles([d('1', 'sys-sw-b', '2930F'), d('2', 'sys-sw-a', '2930F'), d('3', 'x', 'FortiGate-101F')]);
    expect(roles.aruba_a?.id).toBe('2');
    expect(roles.aruba_b?.id).toBe('1');
    expect(roles.firewall?.id).toBe('3');
    expect(roles.blackbox).toBeUndefined();
  });

  it('without names, the bench address decides which 2930F plays which role', () => {
    const d = (id: string, address: string) => ({ id, name: `sw${id}`, model: '2930F', management_address: address } as Device);
    const roles = assignRoles([d('1', '192.168.1.2'), d('2', '192.168.1.1')]);
    expect(roles.aruba_a?.id).toBe('2');
    expect(roles.aruba_b?.id).toBe('1');
  });
});

describe('login after loading (D-092)', () => {
  const real = (model: string) => ({ id: 'x', model, environment: 'lab', capabilities: [] } as unknown as Device);
  const sim = (model: string) => ({ id: 'x', model, environment: 'simulated', capabilities: [] } as unknown as Device);

  it('a real Black Box needs it: its team file sets the approved password', () => {
    const c = { ...EMPTY_CHOICE, fileId: 'f' };
    expect(planSteps(role('blackbox'), c, real('LIG1014A')).missing).toEqual(['the login after loading (its team file sets the approved password)']);
    const ok = planSteps(role('blackbox'), { ...c, loginAfter: 'approved' }, real('LIG1014A'));
    expect(ok.missing).toEqual([]);
    expect(ok.steps).toEqual([{ kind: 'configuration', version_id: 'f', credential_after_ref_id: 'approved' }]);
  });

  it('not for a simulated Black Box, nor a 2930F (its console setup gave it the approved login)', () => {
    expect(planSteps(role('blackbox'), { ...EMPTY_CHOICE, fileId: 'f' }, sim('LIG1014A')).missing).toEqual([]);
    expect(planSteps(role('aruba_a'), { ...EMPTY_CHOICE, fileId: 'f' }, real('2930F')).missing).toEqual([]);
  });

  it('a real FortiGate needs it for its base file', () => {
    const c = { ...EMPTY_CHOICE, firstLogin: false, baseId: 'b', siteId: 's' };
    expect(planSteps(role('firewall'), c, real('FortiGate-101F')).missing).toEqual(['the login after loading (its base file sets its own admin password)']);
  });
});

describe('two devices ending at one address (D-091)', () => {
  const sw = (id: string, address: string) => ({ device: { id, name: `sw-${id}`, model: '2930F', management_address: address } as Device });
  const b = ROLES.find((r) => r.key === 'aruba_b')!;
  const a = ROLES.find((r) => r.key === 'aruba_a')!;

  it('the switch on its temporary address waits for the one already at the final address', () => {
    const all = [sw('a', '192.168.1.1'), sw('b', '192.168.1.2')];
    expect(addressTakenBy(b, all[1].device, all)?.id).toBe('a');
    expect(addressTakenBy(a, all[0].device, all)).toBeUndefined();  // its file keeps its address
  });

  it('nothing to wait for once moved, or with one switch only', () => {
    const moved = [sw('a', '192.168.1.1'), sw('b', '192.168.1.1')];
    expect(addressTakenBy(b, moved[1].device, moved)).toBeUndefined();
    const alone = [sw('b', '192.168.1.2')];
    expect(addressTakenBy(b, alone[0].device, alone)).toBeUndefined();
  });
});

describe('device address check', () => {
  it('accepts addresses and host names, refuses the rest', async () => {
    const { addressProblem } = await import('../src/services/validation');
    for (const ok of ['', '192.0.2.1', 'switch-1.example.net', 'fe80::1']) expect(addressProblem(ok)).toBeNull();
    for (const bad of ['192.0.2.300', '192.0.2.1/24', '192.0.2.1:22', 'two words']) expect(addressProblem(bad)).not.toBeNull();
  });
});

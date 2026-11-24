import { describe, expect, it } from 'vitest';

import { EMPTY_CHOICE, planSteps } from '../src/features/stage/choices';
import { assignRoles, ROLES } from '../src/features/stage/roles';
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

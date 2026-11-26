import { describe, expect, it } from 'vitest';

import { AUDIT_ACTIONS } from '../src/services/labels';

/** Every audit action the backend records has words in the Audit log (D-123). Read from the
 *  backend's own source, so a new action without a label fails here. */
const backend = import.meta.glob('../../backend/src/undm/**/*.py', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

describe('audit log words (D-123)', () => {
  it('reads the backend source', () => {
    expect(Object.keys(backend).length).toBeGreaterThan(20);
  });

  it('every recorded action has a label', () => {
    const found = new Set<string>();
    for (const text of Object.values(backend)) {
      for (const m of text.matchAll(/audit\.record\(\s*[^,]+,\s*[^,]+,\s*"([a-z_]+(?:\.[a-z_]+)+)"/g)) found.add(m[1]);
      // device.<operation>: the read-only operations a person runs from the device menu.
      if (text.includes('f"device.{op.value}"')) {
        for (const op of ['get_facts', 'check_reachability', 'get_running_configuration', 'backup_configuration', 'get_firmware_information']) {
          found.add(`device.${op}`);
        }
      }
    }
    expect(found.size).toBeGreaterThan(40);
    const missing = [...found].filter((a) => !AUDIT_ACTIONS[a]).sort();
    expect(missing).toEqual([]);
  });
});

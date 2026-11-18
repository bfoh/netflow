import type { DeviceIntent } from '../types/api';

/** Stored intent may omit empty lists (e.g. older or hand-written data); fill them in. */
export function normalizeIntent(intent: Partial<DeviceIntent> | null | undefined, name: string): DeviceIntent {
  return {
    hostname: intent?.hostname ?? name,
    vlans: intent?.vlans ?? [],
    interfaces: intent?.interfaces ?? [],
    static_routes: intent?.static_routes ?? [],
  };
}

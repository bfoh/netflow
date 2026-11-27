/**
 * Every address in the app, in one place (D-120). Pages link with these, never with written
 * URLs, so a page can move without broken links. Old addresses redirect (routes.tsx).
 */
const q = (params: Record<string, string | number | null | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') s.set(k, String(v));
  const text = s.toString();
  return text ? `?${text}` : '';
};

export type SettingsTab = 'logins' | 'templates' | 'certificate' | 'safety' | 'identity' | 'about';
export type DeviceTab = 'overview' | 'files' | 'log' | 'troubleshoot' | 'intent';
export type SystemTab = 'devices' | 'network' | 'plans' | 'logins' | 'settings';

export const paths = {
  home: '/',
  /** Stage a system: the last unfinished one, or the chooser. */
  stage: (systemId?: string, step?: number, extra: Record<string, string | undefined> = {}) =>
    (systemId ? `/stage/${systemId}` : '/stage') + q({ step, ...extra }),
  stageChooser: '/stage?choose=1',
  /** A device's card in the Run step (step 4), scrolled into view. */
  stageCard: (systemId: string, deviceId: string) => `/stage/${systemId}` + q({ step: 3 }) + `#device-${deviceId}`,
  systems: '/systems',
  system: (id: string, tab?: SystemTab) => `/systems/${id}` + q({ tab }),
  devices: '/devices',
  device: (id: string, tab?: DeviceTab, version?: string) => `/devices/${id}` + q({ tab, version }),
  plans: '/plans',
  /** A new plan, with its system, devices and file chosen (Advanced). */
  planNew: (p: { system?: string; devices?: string; version?: string } = {}) => '/plans/new' + q(p),
  plan: (id: string) => `/plans/${id}`,
  staging: (id: string) => `/plans/staging/${id}`,
  /** The console tool (Advanced): console setup of one device. */
  console: (deviceId?: string) => '/console' + q({ device: deviceId }),
  firmware: (model?: string) => '/firmware' + q({ model }),
  topology: '/topology',
  audit: '/audit',
  settings: (tab?: SettingsTab) => '/settings' + q({ tab }),
} as const;

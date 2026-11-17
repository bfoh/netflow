import { Badge, Tooltip } from '@mantine/core';

import type { DeviceEnvironment } from '../types/api';

const ENV: Record<DeviceEnvironment, { color: string; label: string; hint: string }> = {
  simulated: { color: 'violet', label: 'SIMULATED',
    hint: 'Exists only in the UNDM simulation lab. No physical device is contacted.' },
  lab: { color: 'yellow', label: 'LAB', hint: 'Real equipment in an approved, isolated laboratory.' },
  production: { color: 'red', label: 'PRODUCTION', hint: 'Real equipment carrying live traffic.' },
};

export function EnvironmentBadge({ env }: { env: DeviceEnvironment }) {
  const e = ENV[env] ?? ENV.simulated;
  return (
    <Tooltip label={e.hint} withArrow>
      <Badge color={e.color} variant="light" radius="sm">{e.label}</Badge>
    </Tooltip>
  );
}

const STATE_COLOR: Record<string, string> = {
  draft: 'gray', validating: 'blue', awaiting_approval: 'orange', ready: 'cyan',
  preflight: 'blue', backing_up: 'blue', deploying: 'blue', verifying: 'blue', recovering: 'orange',
  succeeded: 'teal', failed: 'red', rolled_back: 'orange', recovery_required: 'red', cancelled: 'gray',
  // target and device states
  verified: 'teal', in_sync: 'teal', no_change: 'teal', previewed: 'cyan', pending: 'gray',
  never_deployed: 'gray', unknown: 'yellow', deployment_failed: 'red', manual_recovery_required: 'red',
  skipped: 'gray', success: 'teal', unsupported: 'yellow', ok: 'teal', error: 'red',
};

export function StateBadge({ state }: { state: string }) {
  return (
    <Badge color={STATE_COLOR[state] ?? 'gray'} variant="light" radius="sm">
      {state.replaceAll('_', ' ')}
    </Badge>
  );
}

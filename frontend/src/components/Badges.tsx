import { Badge, Tooltip } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconX } from '@tabler/icons-react';

import { stateColor, stateHint, stateLabel } from '../services/labels';
import type { DeviceEnvironment } from '../types/api';

const ENV: Record<DeviceEnvironment, { color: string; label: string; hint: string }> = {
  simulated: { color: 'violet', label: 'Simulated',
    hint: 'Exists only inside UNDM, for practice. No physical device is contacted.' },
  lab: { color: 'yellow', label: 'Real device', hint: 'Real equipment on an isolated bench.' },
  production: { color: 'red', label: 'Production', hint: 'Real equipment carrying live traffic.' },
};

export function EnvironmentBadge({ env }: { env: DeviceEnvironment }) {
  const e = ENV[env] ?? ENV.simulated;
  return (
    <Tooltip label={e.hint} withArrow>
      <Badge color={e.color} variant="light" radius="sm" style={{ flexShrink: 0 }}
        styles={{ root: { overflow: 'visible' }, label: { overflow: 'visible' } }}>{e.label}</Badge>
    </Tooltip>
  );
}

/** A plan, step or device state in words, with its colour (see services/labels). */
export function StateBadge({ state }: { state: string }) {
  const color = stateColor(state);
  // An icon as well as the colour, so the meaning does not depend on seeing colours.
  const Icon = color === 'red' ? IconX : color === 'orange' || color === 'yellow' ? IconAlertTriangle
    : color === 'teal' ? IconCheck : null;
  // Never cut the label short in a narrow table column.
  const badge = <Badge color={color} variant="light" radius="sm" style={{ flexShrink: 0 }}
    leftSection={Icon ? <Icon size={11} stroke={2.2} aria-hidden /> : undefined}
    styles={{ root: { overflow: 'visible' }, label: { overflow: 'visible' } }}>{stateLabel(state)}</Badge>;
  const hint = stateHint(state);
  return hint ? <Tooltip label={hint} withArrow>{badge}</Tooltip> : badge;
}

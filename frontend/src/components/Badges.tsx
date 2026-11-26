import { Badge, type BadgeProps } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconX } from '@tabler/icons-react';
import type { ReactNode } from 'react';

import { stateColor, stateLabel } from '../services/labels';
import type { DeviceEnvironment } from '../types/api';

/** The only colours a tag may have (D-119): what each means, not which hue. */
export type Tone = 'info' | 'success' | 'warning' | 'danger' | 'neutral' | 'simulated';
const TONE_COLOR: Record<Tone, string> = {
  info: 'blue', success: 'teal', warning: 'orange', danger: 'red', neutral: 'gray', simulated: 'violet',
};

const keepWhole = { root: { overflow: 'visible' }, label: { overflow: 'visible' } } as const;

/** A small label with a meaning (Staged, Experimental, Not verified…). Its colour comes from
 *  its tone, never picked by hand (D-119); size, variant and spacing pass through. */
export function Tag({ tone = 'neutral', children, icon, ...rest }: { tone?: Tone; children: ReactNode; icon?: ReactNode }
  & Omit<BadgeProps, 'color' | 'children' | 'leftSection'> & { title?: string }) {
  return <Badge color={TONE_COLOR[tone]} style={{ flexShrink: 0 }} leftSection={icon} styles={keepWhole} {...rest}>{children}</Badge>;
}

const ENV: Record<DeviceEnvironment, { tone: Tone; label: string }> = {
  simulated: { tone: 'simulated', label: 'Simulated' },
  lab: { tone: 'warning', label: 'Real device' },
  production: { tone: 'danger', label: 'Production' },
};

export function EnvironmentBadge({ env }: { env: DeviceEnvironment }) {
  const e = ENV[env] ?? ENV.simulated;
  return <Tag tone={e.tone}>{e.label}</Tag>;
}

/** A plan, step or device state in words, with its colour and an icon (see services/labels),
 *  so the meaning does not depend on seeing colours. */
export function StateBadge({ state }: { state: string }) {
  const color = stateColor(state);
  const Icon = color === 'red' ? IconX : color === 'orange' || color === 'yellow' ? IconAlertTriangle
    : color === 'teal' ? IconCheck : null;
  return (
    <Badge color={color} style={{ flexShrink: 0 }} styles={keepWhole}
      leftSection={Icon ? <Icon size={12} stroke={2.2} aria-hidden /> : undefined}>{stateLabel(state)}</Badge>
  );
}

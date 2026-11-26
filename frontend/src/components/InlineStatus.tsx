import { Group, Text } from '@mantine/core';
import { IconAlertTriangle, IconCircleCheck, IconInfoCircle, IconX } from '@tabler/icons-react';
import type { ReactNode } from 'react';

import type { Tone } from './Badges';

const LOOK: Record<Exclude<Tone, 'simulated'>, { color: string; Icon: typeof IconX }> = {
  info: { color: 'blue', Icon: IconInfoCircle },
  success: { color: 'teal', Icon: IconCircleCheck },
  warning: { color: 'orange', Icon: IconAlertTriangle },
  danger: { color: 'red', Icon: IconX },
  neutral: { color: 'dimmed', Icon: IconInfoCircle },
};

/** A one-line status next to what it is about (e.g. "Still needed: the SCF"): an icon and
 *  words in an AA colour, never colour alone (D-119). For boxes, use Notice. */
export function InlineStatus({ tone, children, size = 'xs' }: { tone: Exclude<Tone, 'simulated'>; children: ReactNode; size?: 'xs' | 'sm' }) {
  const { color, Icon } = LOOK[tone];
  return (
    <Group gap={6} wrap="nowrap" align="flex-start">
      <Text c={color} size={size} style={{ lineHeight: 0, paddingTop: 2 }} aria-hidden><Icon size={14} /></Text>
      <Text c={color} size={size} component="div">{children}</Text>
    </Group>
  );
}

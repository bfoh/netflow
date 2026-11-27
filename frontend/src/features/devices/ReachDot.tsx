import { Box, Tooltip } from '@mantine/core';

import type { Reachability } from '../../services/api';

const LOOK: Record<string, { color: string; label: string }> = {
  answers: { color: 'var(--mantine-color-teal-6)', label: 'Answers on its management port' },
  no_answer: { color: 'var(--mantine-color-red-6)', label: 'No answer on its management port' },
  simulated: { color: 'var(--mantine-color-violet-4)', label: 'Simulated device' },
  no_address: { color: 'var(--mantine-color-gray-5)', label: 'No management address' },
  no_network_address: { color: 'var(--mantine-color-gray-5)', label: 'No network address yet' },
};

/** A dot for the live reachability of a device (D-099); grey while not yet known. */
export function ReachDot({ state }: { state?: Reachability['state'] }) {
  const look = (state && LOOK[state]) || { color: 'var(--mantine-color-gray-4)', label: 'Checking…' };
  return (
    <Tooltip label={look.label}>
      <Box component="span" role="img" aria-label={look.label}
        style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 9, background: look.color, flexShrink: 0 }} />
    </Tooltip>
  );
}

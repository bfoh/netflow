import { Group, Paper, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconBuildingBroadcastTower, IconFlame, IconQuestionMark, IconRouter, IconServer, IconSwitchHorizontal } from '@tabler/icons-react';
import { Handle, type NodeProps, type Node, Position } from '@xyflow/react';

import { EnvironmentBadge } from '../../components/Badges';
import type { TopologyNode } from '../../types/api';

export type DeviceNodeType = Node<{ device: TopologyNode }, 'device'>;

const ICON: Record<string, typeof IconRouter> = {
  switch: IconSwitchHorizontal, router: IconRouter, firewall: IconFlame, server: IconServer,
  access_point: IconBuildingBroadcastTower, wireless_controller: IconBuildingBroadcastTower,
};
const COLOR: Record<string, string> = { switch: 'blue', router: 'grape', firewall: 'red', server: 'gray' };

export function DeviceNode({ data, selected }: NodeProps<DeviceNodeType>) {
  const d = data.device;
  const Icon = ICON[d.category] ?? IconQuestionMark;
  return (
    <Paper withBorder shadow={selected ? 'md' : 'xs'} p="xs" radius="md" miw={170}
      style={{ borderColor: selected ? 'var(--mantine-primary-color-filled)' : undefined }}>
      {[Position.Top, Position.Right, Position.Bottom, Position.Left].map((p) => (
        <Handle key={p} type="source" position={p} id={p} style={{ width: 9, height: 9 }} />
      ))}
      <Group gap="xs" wrap="nowrap">
        <ThemeIcon variant="light" color={COLOR[d.category] ?? 'gray'} size="lg"><Icon size={18} /></ThemeIcon>
        <Stack gap={0}>
          <Text fw={600} size="sm">{d.name}</Text>
          <Text size="xs" c="dimmed">{d.manufacturer} {d.model}</Text>
          <Group mt={2}><EnvironmentBadge env={d.environment} /></Group>
        </Stack>
      </Group>
    </Paper>
  );
}

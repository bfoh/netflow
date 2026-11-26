import { Card, Checkbox, Group, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconBuildingBroadcastTower, IconDeviceDesktop, IconFolder, IconRouter, IconShieldLock, IconSwitchHorizontal } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';

import type { Reachability } from '../../services/api';
import type { Device } from '../../types/api';
import { DeviceMenu } from '../devices/DeviceMenu';
import { openDeviceMenu } from '../devices/openDeviceMenu';
import { ReachDot } from '../devices/ReachDot';
import { paths } from '../../paths';

/** Groups of a system's devices by kind, in the order people look for them. */
const GROUPS: { key: string; title: string; icon: ReactNode; match: (d: Device) => boolean }[] = [
  { key: 'firewall', title: 'Firewalls', icon: <IconShieldLock size={16} />, match: (d) => d.category === 'firewall' },
  { key: 'router', title: 'Routers', icon: <IconRouter size={16} />, match: (d) => d.category === 'router' },
  { key: 'switch', title: 'Switches', icon: <IconSwitchHorizontal size={16} />, match: (d) => d.category === 'switch' },
  { key: 'other', title: 'Other devices', icon: <IconDeviceDesktop size={16} />, match: () => true },
];

/**
 * The system as a tree (D-099): its devices grouped by kind, each with its reachability dot,
 * a tick box (shared with the table) and the device menu on right-click or "⋯".
 */
export function SystemTree({ name, devices, selected, onSelectedChange, reach }: {
  name: string; devices: Device[]; selected: string[]; onSelectedChange: (ids: string[]) => void;
  reach?: Map<string, Reachability['state']>;
}) {
  const navigate = useNavigate();
  const placed = new Set<string>();
  const groups = GROUPS.map((g) => {
    const members = devices.filter((d) => !placed.has(d.id) && g.match(d));
    members.forEach((d) => placed.add(d.id));
    return { ...g, members };
  }).filter((g) => g.members.length > 0);
  const toggle = (ids: string[], on: boolean) =>
    onSelectedChange(on ? [...new Set([...selected, ...ids])] : selected.filter((x) => !ids.includes(x)));
  return (
    <Card withBorder padding="sm" aria-label={`Devices of ${name}`}>
      <Group gap={6} mb={6} wrap="nowrap"><IconBuildingBroadcastTower size={16} /><Text fw={600} size="sm" truncate>{name}</Text></Group>
      <Stack gap={6} pl="xs">
        {groups.map((g) => {
          const ids = g.members.map((d) => d.id);
          const all = ids.every((id) => selected.includes(id));
          const some = ids.some((id) => selected.includes(id));
          return (
            <Stack key={g.key} gap={2}>
              <Group gap={6} wrap="nowrap">
                <Checkbox size="xs" aria-label={`Select all ${g.title.toLowerCase()}`} checked={all} indeterminate={some && !all}
                  onChange={() => toggle(ids, !all)} />
                <IconFolder size={16} /><Text size="sm">{g.title}</Text>
                <Text size="xs" c="dimmed">({g.members.length})</Text>
              </Group>
              {g.members.map((d) => (
                <Group key={d.id} gap={6} pl="lg" wrap="nowrap" onContextMenu={openDeviceMenu}>
                  <Checkbox size="xs" aria-label={`Select ${d.name}`} checked={selected.includes(d.id)}
                    onChange={(e) => toggle([d.id], e.currentTarget.checked)} />
                  {g.icon}
                  {reach && <ReachDot state={reach.get(d.id)} />}
                  <UnstyledButton onClick={() => void navigate(paths.device(d.id))} style={{ flex: 1, minWidth: 0 }}>
                    <Text size="sm" truncate>{d.name}</Text>
                  </UnstyledButton>
                  <DeviceMenu device={d} />
                </Group>
              ))}
            </Stack>
          );
        })}
        {groups.length === 0 && <Text size="sm" c="dimmed">No devices yet.</Text>}
      </Stack>
    </Card>
  );
}

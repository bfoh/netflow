import { Anchor, Badge, Button, Card, Code, Group, List, Stack, Table, Text, Title } from '@mantine/core';
import { IconPlugConnected, IconTerminal2 } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../../components/Badges';
import { Hint } from '../../components/Hint';
import { SafetyHint } from '../../components/SafetyHint';
import { useAction, usePolicy } from '../../hooks/queries';
import { api } from '../../services/api';
import type { Device, OperationResult } from '../../types/api';
import { addressTakenBy, type Role } from './roles';
import { Notice } from '../../components/Notice';

const CONSOLE_DONE = new Set(['bootstrapped', 'managed']);

/** Step 3: cabling, safety switches, and whether each device answers. */
export function BenchStep({ roles }: { roles: { role: Role; device: Device }[] }) {
  const policy = usePolicy();
  const [results, setResults] = useState<Record<string, OperationResult>>({});
  const test = useAction(async (d: Device) => {
    const r = await api.runOperation(d.id, 'check_reachability');
    setResults((prev) => ({ ...prev, [d.id]: r }));
    return r;
  });
  const real = roles.some(({ device }) => device.environment !== 'simulated');
  return (
    <Stack>
      <Card withBorder>
        <Title order={3} size="h5" mb="xs">Cabling</Title>
        <List size="sm" spacing={4} mb="sm">
          <List.Item>Connect the PC and every device to one small switch that is connected to nothing else, with one cable per device (two would make a loop).</List.Item>
          <List.Item>Give the PC's wired adapter two addresses, one per factory network, for example <Code>192.168.1.50/24</Code> and <Code>192.0.2.50/24</Code> (Windows: adapter settings → IPv4 → Advanced). UNDM does not change your PC's network settings.</List.Item>
          <List.Item>Aruba switches: the USB console cable goes to the PC first, for the console setup. One cable is enough: move it from one switch to the other.</List.Item>
          <List.Item>Allow incoming TFTP on this PC (UDP port 69): devices fetch firmware and files from UNDM. A blocked transfer is reported as such.</List.Item>
        </List>
        <Table.ScrollContainer minWidth={560}>
          <Table verticalSpacing={4} aria-label="Cabling per device">
            <Table.Thead><Table.Tr><Table.Th>Device</Table.Th><Table.Th>Cable</Table.Th><Table.Th>Address now</Table.Th><Table.Th>After its file</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {roles.map(({ role, device }) => (
                <Table.Tr key={role.key}>
                  <Table.Td><Text size="sm" fw={600}>{role.title}</Text></Table.Td>
                  <Table.Td><Text size="sm">{role.cable}</Text></Table.Td>
                  <Table.Td><Text size="sm" ff="monospace">{device.management_address || '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm" ff="monospace">{device.management_address === role.addressAfter ? 'same' : role.addressAfter}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {roles.map(({ role, device }) => {
          const other = addressTakenBy(role, device, roles);
          return other ? (
            <Notice key={role.key} kind="caution" compact mt="sm">
              {device.name} and {other.name} both end at {role.addressAfter}. Run {other.name} first; when it shows
              Staged, unplug it from the small switch, then run {device.name}.
            </Notice>
          ) : null;
        })}
      </Card>
      {real && <><SafetyHint real /><SafetyHint real firmware /></>}
      {real && policy.data?.firmware_require_separate_approver !== false && (
        <Hint>Staging alone? Firmware plans need a second person to approve them, unless you turn that off in{' '}
          <Anchor component={Link} to="/settings" size="xs">Settings → Safety</Anchor>.</Hint>
      )}
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="sm" horizontalSpacing="md">
            <Table.Thead><Table.Tr><Table.Th>Device</Table.Th><Table.Th>Address</Table.Th><Table.Th>Console setup</Table.Th><Table.Th>Test connection</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {roles.map(({ role, device }) => {
                const r = results[device.id];
                const needsConsole = role.steps.includes('console');
                return (
                  <Table.Tr key={role.key}>
                    <Table.Td>
                      <Anchor component={Link} to={`/devices/${device.id}`} fw={600} size="sm">{device.name}</Anchor>
                      <Group gap={6} mt={2}><Text size="xs" c="dimmed">{role.title}</Text><EnvironmentBadge env={device.environment} /></Group>
                    </Table.Td>
                    <Table.Td><Text size="sm" ff="monospace">{device.management_address || '—'}</Text></Table.Td>
                    <Table.Td>
                      {needsConsole ? (
                        CONSOLE_DONE.has(device.provisioning_status)
                          ? <StateBadge state={device.provisioning_status} />
                          : <Button size="xs" variant="light" component={Link} to={`/provisioning?device=${device.id}`}
                            leftSection={<IconTerminal2 size={14} />}>Open console setup</Button>
                      ) : <Text size="sm" c="dimmed">Not needed</Text>}
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button size="xs" variant="light" leftSection={<IconPlugConnected size={14} />}
                          loading={test.isPending && test.variables?.id === device.id} onClick={() => test.mutate(device)}>Test</Button>
                        {r && <Badge color={r.status === 'success' ? 'teal' : 'red'} variant="light" tt="none">
                          {r.status === 'success' ? 'Connected' : 'Did not connect'}</Badge>}
                      </Group>
                      {r && r.status !== 'success' && <Text size="xs" c="red" mt={2}>{r.message}</Text>}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Text size="xs" c="dimmed">Test connection logs in with the device's login. A new FortiGate refuses the approved login until the plan's first step sets it, so “Did not connect” is expected for it now.</Text>
    </Stack>
  );
}

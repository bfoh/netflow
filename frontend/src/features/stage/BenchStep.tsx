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
import { addressTakenBy, canMoveAside, CONSOLE_DONE, consoleOnly, type Role } from './roles';
import { Notice } from '../../components/Notice';


/** Step 3: cabling, safety switches, and whether each device answers. */
export function BenchStep({ roles }: { roles: { role: Role; device: Device }[] }) {
  const policy = usePolicy();
  // Each answer stays in the device's row; a refused test (e.g. no login chosen) too, so no
  // pop-up covers the table being checked.
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string; loginRefused?: boolean }>>({});
  const test = useAction(async (d: Device) => {
    try {
      const r: OperationResult = await api.runOperation(d.id, 'check_reachability');
      setResults((prev) => ({ ...prev, [d.id]: { ok: r.status === 'success', message: r.message, loginRefused: !!r.login_refused } }));
    } catch (e) {
      setResults((prev) => ({ ...prev, [d.id]: { ok: false, message: e instanceof Error ? e.message : String(e) } }));
    }
  }, undefined, { errorInDialog: true });
  const real = roles.some(({ device }) => device.environment !== 'simulated');
  return (
    <Stack>
      <Card withBorder>
        <Title order={3} size="h5" mb="xs">Cabling</Title>
        <List size="sm" spacing={4} mb="sm">
          <List.Item>Connect the PC and every device to one small switch that is connected to nothing else, with one cable per device (two would make a loop).</List.Item>
          <List.Item>Give the PC's wired adapter two addresses, one per factory network, for example <Code>192.168.1.50/24</Code> and <Code>192.0.2.50/24</Code> (Windows: adapter settings → IPv4 → Advanced). UNDM does not change your PC's network settings.</List.Item>
          <List.Item>Aruba switches: the USB console cable goes to the PC first, for the console setup. One cable is enough: move it from one switch to the other.</List.Item>
          {roles.some(({ role }) => consoleOnly(role)) && (
            <List.Item>Nokia modem: its console cable only, at speed 115200. It is not plugged into the small switch.</List.Item>
          )}
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
                  <Table.Td><Text size="sm" ff="monospace">{!role.addressAfter ? '—' : device.management_address === role.addressAfter ? 'same' : role.addressAfter}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {roles.map(({ role, device }) => {
          const other = addressTakenBy(role, device, roles);
          return other ? (
            <Notice key={role.key} kind="caution" compact mt="sm">
              {device.name} and {other.name} both end at {role.addressAfter}. Run {other.name} first. {canMoveAside(other)
                ? `The plan of ${device.name} then switches off ${other.name}’s management port until its next power-on: no cable to unplug.`
                : `When it shows Staged, unplug it from the small switch, then run ${device.name}.`}
            </Notice>
          ) : null;
        })}
      </Card>
      {real && <><SafetyHint real /><SafetyHint real firmware /></>}
      {real && policy.data?.firmware_require_separate_approver !== false && (
        <Hint>Staging alone? Firmware plans need a second person to approve them, unless you turn that off in{' '}
          <Anchor component={Link} to="/settings?tab=safety" size="xs">Settings → Safety</Anchor>.</Hint>
      )}
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="sm" horizontalSpacing="md">
            <Table.Thead><Table.Tr><Table.Th>Device</Table.Th><Table.Th>Address</Table.Th><Table.Th>Console setup</Table.Th><Table.Th>Test connection</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {roles.map(({ role, device }) => {
                const r = results[device.id];
                const needsConsole = role.steps.includes('console');
                // A factory unit whose plan starts with its first login refuses the approved
                // login until that step sets it: expected, not a problem (never connected yet).
                const expected = !!r && !r.ok && !!r.loginRefused && role.steps[0] === 'first_login'
                  && !device.last_connection_at;
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
                      {consoleOnly(role) ? (
                        <Text size="sm" c="dimmed">Console cable only: no network test</Text>
                      ) : device.environment !== 'simulated' && !device.credential_ref_id ? (
                        <Text size="sm">Choose its login first:{' '}
                          <Anchor component={Link} to="?step=0" size="sm">step 1, “Its login”</Anchor></Text>
                      ) : (
                        <>
                          <Group gap="xs" wrap="nowrap">
                            <Button size="xs" variant="light" leftSection={<IconPlugConnected size={14} />}
                              loading={test.isPending && test.variables?.id === device.id} onClick={() => test.mutate(device)}>Test</Button>
                            {r && <Badge color={r.ok ? 'teal' : expected ? 'gray' : 'red'} variant="light" tt="none">
                              {r.ok ? 'Connected' : expected ? 'Expected now' : 'Did not connect'}</Badge>}
                          </Group>
                          {expected
                            ? <Text size="xs" c="dimmed" mt={2}>A factory FortiGate has no password yet: the first step of its plan logs in as admin with no password and sets this login&apos;s password. Go on to step 4.</Text>
                            : r && !r.ok && <Text size="xs" c="red" mt={2}>{r.message}</Text>}
                        </>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Text size="xs" c="dimmed">Test connection logs in with the device's login.</Text>
    </Stack>
  );
}

import { Anchor, Button, Card, Group, Select, Stack, Table, Text, Title } from '@mantine/core';
import { IconArrowBackUp, IconRoute, IconTerminal } from '@tabler/icons-react';
import { useQueries } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';

import { EnvironmentBadge, Tag } from '../../components/Badges';
import { ActionsHeader, DataTable } from '../../components/DataTable';
import { Hint } from '../../components/Hint';
import { Notice } from '../../components/Notice';
import { useAction, usePolicy } from '../../hooks/queries';
import { useConfirm } from '../../hooks/useConfirm';
import { paths } from '../../paths';
import { api } from '../../services/api';
import type { Device, FileAddresses, Project } from '../../types/api';
import { connectionOf } from '../devices/connection';
import { ConsoleWindowDialog } from '../devices/ConsoleWindowDialog';
import { DeviceMenu } from '../devices/DeviceMenu';
import { ChooseNetworkAddress } from './ChooseNetworkAddress';
import { CopyCommand } from './CopyCommand';
import { gatewayOf, READ_SWITCH_LINE } from './network';

/**
 * After staging (D-125): the system is reached on the bench or in the network, through its
 * BFW. Each device's network address comes from its file, confirmed by a person. Moving the
 * system changes only UNDM's records; it contacts no device and never this PC's network.
 */
export function NetworkTab({ project, devices }: { project: Project; devices: Device[] }) {
  const policy = usePolicy();
  const [ask, confirmDialog] = useConfirm();
  const [choosing, setChoosing] = useState<Device | null>(null);
  const [consoleFor, setConsoleFor] = useState<Device | null>(null);
  const network = project.reached_via === 'network';
  const gateway = gatewayOf(project, devices);
  const real = devices.filter((d) => d.environment !== 'simulated');
  const files = useQueries({ queries: devices.map((d) => ({
    queryKey: ['file-addresses', d.id], queryFn: () => api.fileAddresses(d.id) })) });
  const fileOf = new Map<string, FileAddresses | undefined>(devices.map((d, i) => [d.id, files[i]?.data]));
  const move = useAction((via: 'bench' | 'network') => api.setReachedVia(project.id, via, gateway?.id ?? null),
    (p) => (p.reached_via === 'network' ? `${p.name} is reached in the network now` : `${p.name} is back on the bench`), { errorInDialog: true });
  const setGateway = useAction((id: string) => api.setReachedVia(project.id, project.reached_via ?? 'bench', id), 'BFW chosen');
  const missing = devices.filter((d) => !d.network_address);
  const readOff = real.length > 0 && policy.data && !policy.data.allow_production_read_only;
  const hints = devices.flatMap((d) => (fileOf.get(d.id)?.route_hint ? [{ device: d, hint: fileOf.get(d.id)!.route_hint! }] : []));

  const askMove = () => ask(network ? {
    title: `Move ${project.name} back to the bench?`, confirmLabel: 'Move back to the bench', color: 'blue',
    message: <Stack gap="xs">
      <Text size="sm">UNDM reaches each device at its bench address again, and its real devices are lab devices again.
        Plans, console setup and staging steps can be run again. No device is contacted.</Text>
    </Stack>,
    onConfirm: () => move.mutateAsync('bench'),
  } : {
    title: `Move ${project.name} to the network?`, confirmLabel: 'Move to the network', color: 'blue',
    message: <Stack gap="xs">
      <Text size="sm">UNDM then reaches each device at its network address, through {gateway?.name ?? 'the BFW'}. Connect this PC to
        a port of the BFW. No device is contacted and this PC's network settings are not changed.</Text>
      {real.length > 0 && <Notice kind="caution" compact>
        This may be a live site, so its real devices become <b>production</b> devices. UNDM's own logins to them (Test connection,
        Read information, Back up now, ping and traceroute from a device) then need the start-up setting {READ_SWITCH_LINE}.
        Ping and traceroute from this PC, and the SSH and console windows, always work.</Notice>}
      <Text size="sm">Plans, console setup and staging steps only run on the bench.</Text>
      {missing.length > 0 && <Text size="sm">Still without a network address: {missing.map((d) => d.name).join(', ')}.</Text>}
    </Stack>,
    onConfirm: () => move.mutateAsync('network'),
  });

  return (
    <Stack>
      {confirmDialog}
      <Card withBorder>
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <Stack gap={4} maw={720}>
            <Group gap="xs"><Title order={2}>Where UNDM reaches this system</Title>
              <Tag tone={network ? 'info' : 'neutral'}>{network ? 'In the network' : 'On the bench'}</Tag></Group>
            <Text size="sm">{network
              ? `In the network, through its BFW${gateway ? ` (${gateway.name})` : ''}: each device at its network address.`
              : 'On the bench: each device at its bench address. After staging, set each network address below, then move it to the network.'}</Text>
          </Stack>
          <Button leftSection={network ? <IconArrowBackUp size={16} /> : <IconRoute size={16} />} loading={move.isPending}
            variant={network ? 'default' : 'filled'} onClick={askMove}>{network ? 'Move back to the bench…' : 'Move to the network…'}</Button>
        </Group>
        <Select mt="md" maw={420} label="Its BFW" description="The FortiGate this PC is connected to in the network; it routes to every other device."
          placeholder="Choose the BFW" data={devices.map((d) => ({ value: d.id, label: d.name }))} value={gateway?.id ?? null}
          onChange={(v) => { if (v) setGateway.mutate(v); }} allowDeselect={false} />
      </Card>

      {readOff && (
        <Notice kind={network ? 'caution' : 'status'} live={false}
          title={network ? "UNDM's own logins to these devices are off" : 'In the network, UNDM’s own logins need a start-up setting'}
          details={<Stack gap={6}>
            <Text size="sm">Add this line to backend\.env on this PC, then restart the backend:</Text>
            <CopyCommand value={READ_SWITCH_LINE} label="the setting" />
          </Stack>}>
          In the network its real devices are production devices. Test connection, Read information and Back up now stay off until the
          setting is on; they only read. Ping and traceroute from this PC, and the SSH and console windows, work without it.
        </Notice>
      )}

      <Card withBorder padding={0}>
        <DataTable label="Devices of this system in the network" rowCount={devices.length} minWidth={900}
          empty="No devices yet: add them in Stage a system.">
          <Table.Thead><Table.Tr>
            <Table.Th>Device</Table.Th><Table.Th>Bench address</Table.Th><Table.Th>Network address</Table.Th>
            <Table.Th>UNDM uses</Table.Th><Table.Th>Limits in its file</Table.Th><ActionsHeader />
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            {devices.map((d) => {
              const conn = connectionOf(d);
              const found = fileOf.get(d.id);
              const ssh = d.environment !== 'simulated' && conn.capabilities.includes('supports_ssh') && !!conn.address;
              return (
                <Table.Tr key={d.id}>
                  <Table.Td><Group gap="xs" wrap="nowrap">
                    <Anchor component={Link} to={paths.device(d.id)} fw={600} size="sm">{d.name}</Anchor>
                    <EnvironmentBadge env={d.environment} />{d.id === gateway?.id && <Tag tone="info" size="sm">BFW</Tag>}
                  </Group></Table.Td>
                  <Table.Td><Text size="sm" ff="monospace">{d.management_address || '—'}</Text></Table.Td>
                  <Table.Td><Group gap="xs" wrap="nowrap">
                    <Text size="sm" ff="monospace">{d.network_address || 'Not set'}</Text>
                    <Button size="compact-xs" variant="light" disabled={!!d.locked_by_deployment_id} onClick={() => setChoosing(d)}
                      aria-label={`Choose the network address of ${d.name} from its file`}>
                      {d.network_address ? 'Change…' : 'Choose from its file…'}</Button>
                  </Group></Table.Td>
                  <Table.Td><Text size="sm" ff="monospace">{conn.address || '—'}</Text>
                    {conn.problem && <Text size="xs" c="dimmed">No network address yet</Text>}</Table.Td>
                  <Table.Td><Limits found={found} /></Table.Td>
                  <Table.Td><Group gap={4} wrap="nowrap" justify="flex-end">
                    {d.environment !== 'simulated' && <Button size="compact-xs" variant="default"
                      onClick={() => setConsoleFor(d)}>Console window…</Button>}
                    {ssh && <SshButton device={d} />}
                    <DeviceMenu device={d} />
                  </Group></Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </DataTable>
      </Card>

      {hints.length > 0 && (
        <Card withBorder>
          <Title order={3} mb={4}>If this PC cannot reach a device</Title>
          <Hint mb="sm">A suggestion only: UNDM never changes this PC's network settings. If the BFW is not this PC's default way to
            that network, an administrator can add the route in a Windows command prompt (it lasts until the PC restarts).</Hint>
          <Stack gap="xs">
            {hints.map(({ device, hint }) => (
              <div key={device.id}><Text size="sm" mb={2}>{device.name}</Text><CopyCommand value={hint} label={`the route to ${device.name}`} /></div>
            ))}
          </Stack>
        </Card>
      )}

      {choosing && <ChooseNetworkAddress device={choosing} opened onClose={() => setChoosing(null)} />}
      {consoleFor && <ConsoleWindowDialog device={consoleFor} opened onClose={() => setConsoleFor(null)} />}
    </Stack>
  );
}

function SshButton({ device }: { device: Device }) {
  const ssh = useAction(() => api.openSsh(device.id), () => `SSH window opened for ${device.name}: type the password there`);
  return <Button size="compact-xs" variant="default" leftSection={<IconTerminal size={12} />} loading={ssh.isPending}
    onClick={() => ssh.mutate(undefined)}>SSH window</Button>;
}

function Limits({ found }: { found?: FileAddresses }) {
  if (!found) return <Text size="sm" c="dimmed">—</Text>;
  if (!found.reader) return <Text size="sm" c="dimmed">Not read for this model</Text>;
  if (found.managers.length === 0) return <Text size="sm" c="dimmed">None in its file</Text>;
  if (found.pc_allowed === false) return <Tag tone="warning" title={found.managers.map((m) => m.text).join('; ')}>This PC is outside them</Tag>;
  if (found.pc_allowed) return <Tag tone="success" title={found.managers.map((m) => m.text).join('; ')}>This PC is allowed</Tag>;
  return <Text size="sm">{found.managers.length} in its file</Text>;
}

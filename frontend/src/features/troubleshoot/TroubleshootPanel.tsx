import { Accordion, Anchor, Button, Card, Code, CopyButton, Group, Select, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { IconRoute, IconTerminal2, IconWaveSine } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import { Tag } from '../../components/Badges';
import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { InlineStatus } from '../../components/InlineStatus';
import { ReasonButton } from '../../components/ReasonButton';
import { useAction, useProject, useProjectDevices } from '../../hooks/queries';
import { paths } from '../../paths';
import { api } from '../../services/api';
import type { Device, HopAnswer, PingAnswer, TraceAnswer } from '../../types/api';
import { connectionOf } from '../devices/connection';
import { ConsoleWindowDialog } from '../devices/ConsoleWindowDialog';
import { gatewayOf } from '../network/network';

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;
const ms = (v: number | null) => (v === null ? '*' : `${v} ms`);

/**
 * Ping and traceroute after staging (D-128): from this PC, or from a device of the system
 * whose driver has a documented ping. One address at a time, chosen here. The hops are
 * named by device where exactly one device has the address.
 */
export function TroubleshootPanel({ device }: { device: Device }) {
  const project = useProject(device.project_id);
  const devices = useProjectDevices(device.project_id);
  const all = devices.data ?? [];
  const bfw = project.data ? gatewayOf(project.data, all) : undefined;
  const [source, setSource] = useState('pc');
  const [target, setTarget] = useState(connectionOf(device).address);
  const [result, setResult] = useState<{ kind: 'ping'; answer: PingAnswer } | { kind: 'trace'; answer: TraceAnswer } | null>(null);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const canPing = (d: Device) => connectionOf(d).capabilities.includes('supports_ping');
  const sources = [{ value: 'pc', label: 'This PC' },
    ...(bfw && bfw.id !== device.id && canPing(bfw) ? [{ value: bfw.id, label: `${bfw.name} (the BFW)` }] : []),
    ...(canPing(device) ? [{ value: device.id, label: `${device.name} (this device)` }] : [])];
  const ping = useAction(() => api.ping(device.project_id, { source, target: target.trim() }),
    undefined, { errorInDialog: true });
  const trace = useAction(() => api.traceroute(device.project_id, { source, target: target.trim() }),
    undefined, { errorInDialog: true });
  const names = new Map(all.map((d) => [d.id, d]));
  const valid = IPV4.test(target.trim());

  return (
    <Stack>
      <Card withBorder>
        <Title order={2} mb="xs">Ping and traceroute</Title>
        <Text size="sm" c="dimmed" mb="sm">One address at a time. From this PC, UNDM runs Windows' ping and tracert; from a device,
          its own command where its driver documents one. Nothing is changed anywhere.</Text>
        <Group align="flex-end" wrap="wrap">
          <Select label="From" data={sources} value={source} onChange={(v) => setSource(v ?? 'pc')} allowDeselect={false} w={260} />
          <TextInput label="To" value={target} onChange={(e) => setTarget(e.currentTarget.value)} w={220}
            placeholder="for example 198.51.100.10"
            error={target.trim() && !valid ? 'One IPv4 address' : undefined} />
          <ReasonButton leftSection={<IconWaveSine size={16} />} disabled={!valid} reason={!valid ? 'Choose or type one address.' : null}
            loading={ping.isPending} onClick={() => ping.mutate(undefined, { onSuccess: (a) => setResult({ kind: 'ping', answer: a }) })}>Ping</ReasonButton>
          <ReasonButton variant="default" leftSection={<IconRoute size={16} />} disabled={!valid} reason={!valid ? 'Choose or type one address.' : null}
            loading={trace.isPending} onClick={() => trace.mutate(undefined, { onSuccess: (a) => setResult({ kind: 'trace', answer: a }) })}>Traceroute</ReasonButton>
          {device.environment !== 'simulated' && <Button variant="subtle" leftSection={<IconTerminal2 size={16} />}
            onClick={() => setConsoleOpen(true)}>Console window…</Button>}
        </Group>
        <Group gap="xs" mt="sm" wrap="wrap" aria-label="Addresses of this system">
          {all.filter((d) => connectionOf(d).address).map((d) => (
            <Button key={d.id} size="compact-xs" variant={connectionOf(d).address === target.trim() ? 'light' : 'subtle'}
              onClick={() => setTarget(connectionOf(d).address)}>{d.name} · {connectionOf(d).address}</Button>
          ))}
        </Group>
        {sources.length === 1 && <Hint mt="sm">From the BFW or this device: when its driver has a documented ping command
          (they are listed on the Drivers page).</Hint>}
        <DialogError error={ping.error ?? trace.error} />
      </Card>

      {result?.kind === 'ping' && <PingCard answer={result.answer} />}
      {result?.kind === 'trace' && <TraceCard answer={result.answer} names={names} />}
      {consoleOpen && <ConsoleWindowDialog device={device} opened onClose={() => setConsoleOpen(false)} />}
    </Stack>
  );
}

function Raw({ raw, summary }: { raw: string; summary: string }) {
  return (
    <Group justify="space-between" align="flex-start" mt="sm">
      {raw ? (
        <Accordion variant="contained" style={{ flex: 1 }}>
          <Accordion.Item value="raw">
            <Accordion.Control>Technical details</Accordion.Control>
            <Accordion.Panel><Code block style={{ whiteSpace: 'pre-wrap' }}>{raw.trim()}</Code></Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      ) : <span />}
      <CopyButton value={raw ? `${summary}\n\n${raw.trim()}` : summary}>
        {({ copied, copy }) => <Button size="xs" variant="default" onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>}
      </CopyButton>
    </Group>
  );
}

function PingCard({ answer }: { answer: PingAnswer }) {
  const times = answer.rtt_ms.length ? ` · ${Math.min(...answer.rtt_ms)}–${Math.max(...answer.rtt_ms)} ms` : '';
  const summary = `Ping ${answer.target}: ${answer.received} of ${answer.sent} replies${times}`;
  return (
    <Card withBorder>
      <Group gap="xs" mb={4}><Title order={3}>Ping {answer.target}</Title>{answer.simulated && <Tag tone="simulated">Simulated</Tag>}</Group>
      <InlineStatus tone={answer.received === answer.sent ? 'success' : answer.received ? 'warning' : 'danger'}>
        {answer.received} of {answer.sent} replies{times}</InlineStatus>
      {answer.note && <Text size="sm" c="dimmed" mt={4}>{answer.note}</Text>}
      <Raw raw={answer.raw} summary={summary} />
    </Card>
  );
}

function TraceCard({ answer, names }: { answer: TraceAnswer; names: Map<string, Device> }) {
  const summary = `Traceroute to ${answer.target}: ` + answer.hops.map((h) => `${h.n} ${h.address ?? '*'}`).join(', ');
  return (
    <Card withBorder>
      <Group gap="xs" mb={4}><Title order={3}>Traceroute to {answer.target}</Title>
        {answer.simulated && <Tag tone="simulated">Simulated</Tag>}
        <Tag tone={answer.reached ? 'success' : 'warning'}>{answer.reached ? 'reached' : 'not reached'}</Tag></Group>
      {answer.note && <Text size="sm" c="dimmed" mb={4}>{answer.note}</Text>}
      <Table.ScrollContainer minWidth={560}>
        <Table aria-label={`Hops to ${answer.target}`}>
          <Table.Thead><Table.Tr><Table.Th>Hop</Table.Th><Table.Th>Address</Table.Th><Table.Th>Device</Table.Th>
            <Table.Th>Times</Table.Th><Table.Th>Where on it</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {answer.hops.map((h) => <HopRow key={h.n} hop={h} names={names} />)}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Raw raw={answer.raw} summary={summary} />
    </Card>
  );
}

function HopRow({ hop, names }: { hop: HopAnswer; names: Map<string, Device> }) {
  const device = hop.device_id ? names.get(hop.device_id) : undefined;
  return (
    <Table.Tr>
      <Table.Td>{hop.n}</Table.Td>
      <Table.Td><Text size="sm" ff="monospace">{hop.address ?? 'no answer'}</Text></Table.Td>
      <Table.Td>{device ? <Anchor component={Link} to={paths.device(device.id, 'troubleshoot')} size="sm">{device.name}</Anchor>
        : hop.candidates.length ? <Text size="sm">one of {hop.candidates.map((c) => names.get(c)?.name ?? c).join(', ')}</Text>
          : <Text size="sm" c="dimmed">—</Text>}</Table.Td>
      <Table.Td><Text size="sm">{hop.rtt_ms.map(ms).join(' · ') || '—'}</Text></Table.Td>
      <Table.Td><Text size="sm">{hop.interface ?? '—'}</Text></Table.Td>
    </Table.Tr>
  );
}

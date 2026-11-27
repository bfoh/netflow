import { Button, CopyButton, Group, Modal, Stack, Table, Text, Title } from '@mantine/core';
import { IconCheck, IconCopy, IconListSearch, IconPlugConnected } from '@tabler/icons-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { Tag } from '../../components/Badges';
import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { InlineStatus } from '../../components/InlineStatus';
import { LoadingLines } from '../../components/Page';
import { ReasonButton } from '../../components/ReasonButton';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { Device, NetconfHelloReading, PortAnswer } from '../../types/api';
import { LoginSelect } from '../logins/LoginSelect';
import { asText } from './servicesText';

/**
 * What management services a device offers (D-130), read-only. Without a login: which of
 * SSH, its portal and NETCONF answer, and what each presents by itself. With a login a
 * person chooses, only when NETCONF answers: its <hello> (capabilities and YANG modules).
 */
export function ServicesDialog({ device, opened, onClose }: { device: Device; opened: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const key = ['device-services', device.id];
  const last = useQuery({ queryKey: key, queryFn: () => api.deviceServices(device.id), enabled: opened });
  const [login, setLogin] = useState<string | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: key });
  const read = useAction(() => api.discoverServices(device.id), (r) => `${device.name}: ${r.message}`, { errorInDialog: true });
  const hello = useAction(() => api.netconfHello(device.id, login!), (r) => `${device.name}: ${r.message}`, { errorInDialog: true });
  const data = last.data;
  const services = data?.services;
  const netconfOpen = !!services?.ports.find((p) => p.port === 830)?.open;
  return (
    <Modal opened={opened} onClose={onClose} size="xl" title={`Management services · ${device.name}`}>
      <Stack>
        <Text size="sm">UNDM opens a connection to SSH (22), its web portal (443) and NETCONF (830) and reads only what each presents
          by itself: an SSH identification line, the portal's certificate. It logs in to nothing, sends no request and changes
          nothing on {device.name}.</Text>
        {last.isLoading && <LoadingLines lines={3} />}
        <Group justify="space-between" align="center">
          <Text size="xs" c="dimmed">{services ? `Last read ${fmtDate(services.at)} at ${services.address}` : 'Not read yet.'}</Text>
          <Group gap="xs">
            {data && (services || data.netconf_hello) && <CopyButton value={asText(device, data)}>
              {({ copied, copy }) => <Button variant="default" leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                onClick={copy}>{copied ? 'Copied' : 'Copy the result'}</Button>}
            </CopyButton>}
            <Button leftSection={<IconListSearch size={16} />} loading={read.isPending}
              onClick={() => read.mutate(undefined, { onSuccess: refresh })}>{services ? 'Read them again' : 'Read its services'}</Button>
          </Group>
        </Group>
        <DialogError error={read.error} />
        {services && <Ports reading={services.ports} simulated={services.simulated} />}

        {services && (
          <Stack gap="xs">
            <Title order={3}>NETCONF</Title>
            {netconfOpen ? <>
              <Text size="sm">UNDM logs in once with the login you choose and reads what it announces: its capabilities and YANG
                modules. It sends no request. A refused login is not tried again, so the account cannot be locked by UNDM.</Text>
              <LoginSelect projectId={device.project_id} label="Login to read it with" value={login} onChange={setLogin}
                description="A login of this system or for all systems, kept in Windows Credential Manager (Logins tab of the system page)." />
              <Group justify="flex-end">
                <ReasonButton leftSection={<IconPlugConnected size={16} />} loading={hello.isPending} disabled={!login}
                  reason={!login ? 'Choose a login first.' : null}
                  onClick={() => hello.mutate(undefined, { onSuccess: refresh })}>Read its NETCONF capabilities</ReasonButton>
              </Group>
            </> : <Hint>NETCONF (port 830) did not answer, so UNDM does not try to log in to it.</Hint>}
            <DialogError error={hello.error} />
            {data?.netconf_hello && <Hello reading={data.netconf_hello} />}
          </Stack>
        )}
        <Group justify="flex-end"><Button variant="default" onClick={onClose} data-autofocus>Close</Button></Group>
      </Stack>
    </Modal>
  );
}

function Ports({ reading, simulated }: { reading: PortAnswer[]; simulated: boolean }) {
  return (
    <Stack gap={4}>
      {simulated && <Tag tone="simulated">Simulated: nothing was sent</Tag>}
      <Table aria-label="Management ports" verticalSpacing="xs">
        <Table.Thead><Table.Tr><Table.Th w={70}>Port</Table.Th><Table.Th w={170}>Service</Table.Th><Table.Th w={110}>Answers</Table.Th>
          <Table.Th>What it presented</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {reading.map((p) => (
            <Table.Tr key={p.port}>
              <Table.Td><Text size="sm" ff="monospace">{p.port}</Text></Table.Td>
              <Table.Td><Text size="sm">{p.name}</Text><Text size="xs" c="dimmed">{p.reference}</Text></Table.Td>
              <Table.Td>{p.open ? <Tag tone="success">Answers</Tag> : <Tag tone="neutral">No answer</Tag>}</Table.Td>
              <Table.Td style={{ overflowWrap: 'anywhere' }}>
                {p.banner && <Text size="sm" ff="monospace">{p.banner}</Text>}
                {p.certificate && <Stack gap={0}>
                  <Text size="sm">Certificate: {p.certificate.subject}</Text>
                  <Text size="xs" c="dimmed">Issued by {p.certificate.issuer} · valid until {fmtDate(p.certificate.not_after)}
                    {p.certificate.tls ? ` · ${p.certificate.tls}` : ''}</Text>
                </Stack>}
                {p.note && <Text size="xs" c="dimmed">{p.note}</Text>}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

function Hello({ reading }: { reading: NetconfHelloReading }) {
  if (!reading.ok) {
    return <InlineStatus tone="danger" size="sm">Read {fmtDate(reading.at)} with {reading.login}: {reading.message}</InlineStatus>;
  }
  const modules = reading.modules ?? [];
  return (
    <Stack gap="xs">
      <Group gap="xs">
        <Text size="sm">Read {fmtDate(reading.at)} with {reading.login}: {reading.message}.</Text>
        {reading.simulated && <Tag tone="simulated">Simulated: nothing was sent</Tag>}
      </Group>
      <Text size="xs" c="dimmed">NETCONF {(reading.base_versions ?? []).join(' and ') || 'version not announced'}
        {reading.session_id ? ` · session ${reading.session_id}` : ''}{reading.host_key ? ` · host key ${reading.host_key}` : ''}</Text>
      {reading.note && <Hint>{reading.note}</Hint>}
      {modules.length > 0 && (
        <Table aria-label="YANG modules it announces" verticalSpacing={4}>
          <Table.Thead><Table.Tr><Table.Th>YANG module</Table.Th><Table.Th w={120}>Revision</Table.Th><Table.Th>Namespace</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {modules.map((m) => (
              <Table.Tr key={`${m.name}@${m.revision}`}>
                <Table.Td><Text size="sm" ff="monospace">{m.name}</Text></Table.Td>
                <Table.Td><Text size="sm">{m.revision || '—'}</Text></Table.Td>
                <Table.Td style={{ overflowWrap: 'anywhere' }}><Text size="xs" ff="monospace">{m.namespace}</Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Text size="xs" c="dimmed">{(reading.capabilities ?? []).length} capabilities in all: Copy the result lists them.</Text>
    </Stack>
  );
}

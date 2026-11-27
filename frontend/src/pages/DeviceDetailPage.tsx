import { Accordion, Anchor, Badge, Button, Card, Code, Group, SegmentedControl, SimpleGrid, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { IconEdit, IconPlugConnected, IconRefresh } from '@tabler/icons-react';
import { useDisclosure } from '@mantine/hooks';
import { type ReactNode, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';

import { useConfirm } from '../hooks/useConfirm';

import { EnvironmentBadge, StateBadge, Tag } from '../components/Badges';
import { Hint } from '../components/Hint';
import { Notice } from '../components/Notice';
import { PageHeader, QueryState } from '../components/Page';
import { useSystemCrumbs } from '../features/systems/crumbs';
import { SafetyHint } from '../components/SafetyHint';
import { fmtDate } from '../services/format';
import { ConfigWorkbench } from '../features/configurations/ConfigWorkbench';
import { DiagnosticsButton } from '../features/devices/DiagnosticsButton';
import { LoginSelect } from '../features/logins/LoginSelect';
import { EditDeviceModal } from '../features/devices/EditDeviceModal';
import { IntentEditor } from '../features/devices/IntentEditor';
import { useAction, useDevice, useDeviceLog, useDrivers } from '../hooks/queries';
import { showSuccess } from '../services/notify';
import { DeviceMenu } from '../features/devices/DeviceMenu';
import { TroubleshootPanel } from '../features/troubleshoot/TroubleshootPanel';
import { connectionOf, inNetwork } from '../features/devices/connection';
import { api } from '../services/api';
import type { Device } from '../types/api';
import { portOff } from '../features/stage/roles';
import { auditActionLabel, capabilityLabel, driverLabel, factLabel, humanize, MAIN_FACTS, stateLabel } from '../services/labels';
import { paths } from '../paths';

function Row({ k, v }: { k: string; v: ReactNode }) {
  return <Table.Tr><Table.Td c="dimmed" w={190}>{k}</Table.Td><Table.Td>{v || '—'}</Table.Td></Table.Tr>;
}

/** Command output exactly as the device printed it, one collapsible block per command. */
function RawOutput({ raw }: { raw?: Record<string, string> }) {
  if (!raw || Object.keys(raw).length === 0) return null;
  return (
    <Accordion variant="contained" mt="sm">
      <Accordion.Item value="raw">
        <Accordion.Control><Text size="sm">Raw command output ({Object.keys(raw).length})</Text></Accordion.Control>
        <Accordion.Panel>
          <Stack gap="xs">
            {Object.entries(raw).map(([cmd, out]) => (
              <div key={cmd}>
                <Text size="xs" fw={600} ff="monospace">{cmd}</Text>
                <Code block mah={260} style={{ overflow: 'auto', fontSize: 11 }}>{out}</Code>
              </div>
            ))}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

/** Collapsed block for values only an expert or support needs. */
function Technical({ children, label = 'Technical details' }: { children: ReactNode; label?: string }) {
  return (
    <Accordion variant="contained" mt="sm">
      <Accordion.Item value="tech">
        <Accordion.Control><Text size="sm">{label}</Text></Accordion.Control>
        <Accordion.Panel>{children}</Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

function Overview({ d }: { d: Device }) {
  const op = useAction((o: string) => api.runOperation(d.id, o), (r) => `${stateLabel(r.status)}${r.message ? ` — ${r.message}` : ''}`);
  const drivers = useDrivers();
  // The login is changed where it is shown (D-122).
  const setLogin = useAction((ref: string | null) => api.updateDevice(d.id, { credential_ref_id: ref }), 'Login chosen');
  const facts = d.observed_facts as Record<string, unknown> | null;
  const extra = ((facts?.extra ?? {}) as Record<string, unknown>);
  const flat: Record<string, unknown> = { ...extra, ...(facts ?? {}) };
  delete flat.extra;
  const scalar = (v: unknown) => v !== null && v !== undefined && v !== '' && typeof v !== 'object';
  const main = MAIN_FACTS.filter((k) => scalar(flat[k]));
  const rest = Object.keys(flat).filter((k) => !MAIN_FACTS.includes(k) && k !== 'raw_output' && scalar(flat[k]));
  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      <Card withBorder>
        <Title order={2} mb="xs">What you entered</Title>
        <Table aria-label="What you entered" verticalSpacing={4}><Table.Tbody>
          <Row k="Model" v={`${d.manufacturer} ${d.model}`} />
          <Row k="Role" v={d.role} />
          <Row k="Bench address" v={<Text size="sm" ff="monospace">{d.management_address}</Text>} />
          {(d.network_address || inNetwork(d)) && <Row k="Network address" v={<Text size="sm" ff="monospace">
            {d.network_address || 'Not set yet'}</Text>} />}
          <Row k="Login" v={<LoginSelect projectId={d.project_id} size="xs" maw={260} label={null} placeholder="None yet: choose one"
            value={d.credential_ref_id} disabled={!!d.locked_by_deployment_id} onChange={(v) => setLogin.mutate(v)} />} />
          <Row k="Connects by" v={driverLabel(d.driver_id, drivers.data)} />
          <Row k="Setup" v={<StateBadge state={d.provisioning_status} />} />
          <Row k="Site / rack" v={[d.site, d.rack_location].filter(Boolean).join(' · ')} />
          <Row k="Tags" v={d.tags.map((t) => <Badge key={t} variant="outline" mr={4}>{t}</Badge>)} />
          <Row k="Notes" v={d.notes} />
        </Table.Tbody></Table>
        <Technical>
          <Table aria-label="Technical details" verticalSpacing={4}><Table.Tbody>
            <Row k="Product family" v={d.product_family} />
            <Row k="Hardware revision" v={d.hardware_revision} />
            <Row k="Category" v={humanize(d.category)} />
            <Row k="Expected firmware" v={`${d.os_family} ${d.firmware_version}`.trim()} />
            <Row k="Protocol / port" v={`${d.management_protocol}${d.management_port ? `:${d.management_port}` : ''}`} />
            <Row k="Management VRF" v={d.management_vrf} />
            <Row k="Driver id" v={<code>{d.driver_id}</code>} />
          </Table.Tbody></Table>
        </Technical>
      </Card>
      <Stack>
        <Card withBorder>
          <Group justify="space-between" mb="xs">
            <Title order={2}>What the device reported</Title>
            <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />} loading={op.isPending} onClick={() => op.mutate('get_facts')}>Read information</Button>
          </Group>
          {facts ? (
            <Table aria-label="What the device reported" verticalSpacing={4}><Table.Tbody>
              {main.map((k) => <Row key={k} k={factLabel(k)} v={String(flat[k])} />)}
              <Row k="Retrieved" v={fmtDate(d.facts_retrieved_at)} />
            </Table.Tbody></Table>
          ) : <Text size="sm" c="dimmed">Nothing read yet. Use Read information: the values on the left are what you entered, not what the device says.</Text>}
          {facts && (
            <Technical>
              {rest.length > 0 && (
                <Table aria-label="More values the device reported" verticalSpacing={4}><Table.Tbody>
                  {rest.map((k) => <Row key={k} k={factLabel(k)} v={String(flat[k])} />)}
                </Table.Tbody></Table>
              )}
              <RawOutput raw={extra.raw_output as Record<string, string> | undefined} />
              <Group mt="sm"><DiagnosticsButton device={d} /></Group>
            </Technical>
          )}
        </Card>
        <Card withBorder>
          <Title order={2} mb="xs">Status</Title>
          <Table aria-label="Status" verticalSpacing={4}><Table.Tbody>
            <Row k="Status" v={<StateBadge state={d.deployment_status} />} />
            <Row k="Last connection" v={fmtDate(d.last_connection_at)} />
            <Row k="Last backup" v={fmtDate(d.last_backup_at)} />
            <Row k="Last plan" v={fmtDate(d.last_deployment_at)} />
          </Table.Tbody></Table>
        </Card>
        <Card withBorder>
          <Title order={2} mb="xs">What UNDM can do with it</Title>
          <Group gap={6}>{d.capabilities.map((c) => <Tag key={c} tone="neutral">{capabilityLabel(c)}</Tag>)}</Group>
          <Text size="xs" c="dimmed" mt="xs">{d.environment === 'simulated'
            ? 'A simulated device: this says nothing about real hardware.'
            : 'What UNDM implements for this model. Real-device procedures stay marked experimental until tested on the bench.'}</Text>
        </Card>
      </Stack>
    </SimpleGrid>
  );
}

/** Everything UNDM recorded about this device, newest first (D-099). */
function DeviceLog({ deviceId }: { deviceId: string }) {
  const log = useDeviceLog(deviceId);
  const [show, setShow] = useState('all');
  const rows = (log.data ?? []).filter((r) => show === 'all'
    || (show === 'plans' && (r.source === 'plan' || r.kind.startsWith('deployment.')))
    || (show === 'console' && r.kind.startsWith('provisioning.'))
    || (show === 'tests' && r.source === 'audit' && r.kind.startsWith('device.')));
  const copy = async () => {
    const masked = await api.deviceLog(deviceId, true);
    const text = masked.map((r) => `${r.time} ${r.kind} [${r.status}] ${r.message}`).join('\n');
    await navigator.clipboard?.writeText(text);
    showSuccess('Copied the log (names, addresses and serials masked)');
  };
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <SegmentedControl size="xs" aria-label="Show" value={show} onChange={setShow}
          data={[{ value: 'all', label: 'All' }, { value: 'plans', label: 'Plans' }, { value: 'console', label: 'Console' }, { value: 'tests', label: 'Tests and reads' }]} />
        <Button size="xs" variant="default" onClick={() => void copy()}>Copy (masked)</Button>
      </Group>
      <QueryState isLoading={log.isLoading} error={log.error} />
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={620}>
          <Table aria-label="Device log" verticalSpacing={6} horizontalSpacing="md">
            <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>What</Table.Th><Table.Th>Result</Table.Th><Table.Th>Detail</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map((r, i) => (
              <Table.Tr key={`${r.time}-${i}`}>
                <Table.Td><Text size="xs" style={{ whiteSpace: 'nowrap' }}>{fmtDate(r.time)}</Text></Table.Td>
                <Table.Td><Text size="sm">{r.source === 'audit' ? auditActionLabel(r.kind) : humanize(r.kind.replace('.', ' · '))}</Text>
                  {r.plan_id && <Anchor component={Link} to={paths.plan(r.plan_id)} size="xs">plan</Anchor>}</Table.Td>
                <Table.Td>{r.status ? <StateBadge state={r.status} /> : '—'}</Table.Td>
                <Table.Td><Text size="xs" lineClamp={3}>{r.message || (r.actor ? `by ${r.actor}` : '')}</Text></Table.Td>
              </Table.Tr>
            ))}
            {!log.isLoading && rows.length === 0 && <Table.Tr><Table.Td colSpan={4}><Text c="dimmed" ta="center" p="md">Nothing recorded for this device yet.</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </Stack>
  );
}

/** Shown for platforms that have a console setup procedure. */
/** For a real device: what may happen to it now, in one or two quiet lines (D-089). */
function RealDeviceNotice({ d }: { d: Device }) {
  const drivers = useDrivers();
  const driver = drivers.data?.find((x) => x.driver_id === d.driver_id);
  if (!driver || driver.simulated) return null;
  if (d.environment === 'production') {
    return <Notice kind="error" mb="md" title="Production device">UNDM is for staging on the bench: production devices are blocked.</Notice>;
  }
  return (
    <Stack gap={4} mb="md">
      {!d.credential_ref_id && <Notice kind="caution" compact>No login chosen yet: UNDM cannot connect. Use Edit device.</Notice>}
      <Hint>Real device on your bench, reached over {driver.transport.toUpperCase()}
        {driver.maturity === 'experimental' ? '; its procedures are marked experimental until proven on the bench.' : '.'}</Hint>
      <SafetyHint real />
      {driver.capabilities.includes('supports_firmware_upgrade') && <SafetyHint real firmware />}
    </Stack>
  );
}

export function DeviceDetailPage() {
  const { deviceId = '' } = useParams();
  const device = useDevice(deviceId);
  const crumbs = useSystemCrumbs(device.data?.project_id);
  const [editing, { open: openEdit, close: closeEdit }] = useDisclosure();
  const [ask, confirmDialog] = useConfirm();
  const navigate = useNavigate();
  const del = useAction(() => api.deleteDevice(deviceId), 'Device deleted', { errorInDialog: true });
  const test = useAction(() => api.runOperation(deviceId, 'check_reachability'), (r) => `${stateLabel(r.status)}${r.message ? ` — ${r.message}` : ''}`);
  const [params, setParams] = useSearchParams();
  // `configs` was the Files tab's name before D-120: old links still open it.
  const raw = params.get('tab') ?? 'overview';
  const tab = raw === 'configs' ? 'files' : raw;
  if (!device.data) return <QueryState isLoading={device.isLoading} error={device.error} />;
  const d = device.data;
  return (
    <>
      <PageHeader title={d.name}
        breadcrumbs={crumbs}
        badges={<><EnvironmentBadge env={d.environment} />{d.provisioning_status !== 'planned' && <StateBadge state={d.provisioning_status} />}</>}
        description={`${d.manufacturer} ${d.model}${connectionOf(d).address ? ` · ${connectionOf(d).address}` : ''}${inNetwork(d) ? ' (in the network)' : ''}`}
        secondary={<Button variant="default" leftSection={<IconEdit size={16} />} onClick={openEdit} disabled={!!d.locked_by_deployment_id}>Edit</Button>}
        primary={<Button leftSection={<IconPlugConnected size={16} />} loading={test.isPending} onClick={() => test.mutate(undefined)}>Test connection</Button>}
        more={<DeviceMenu device={d} size="lg" onEdit={openEdit} onDelete={() => ask({
          title: `Delete ${d.name}?`, confirmLabel: 'Delete device', typed: d.name,
          message: 'The device, its files, backups and history are removed from UNDM. The device itself is not touched. Its login stays on the system page.',
          onConfirm: async () => { await del.mutateAsync(); void navigate(paths.system(d.project_id)); },
        })} />} />
      {confirmDialog}
      <RealDeviceNotice d={d} />
      {editing && <EditDeviceModal device={d} opened={editing} onClose={closeEdit} />}
      {portOff(d) && <PortOff device={d} />}
      {d.locked_by_deployment_id && (
        <Notice kind="status" mb="md" title="A plan is running on this device"
          action={<Anchor component={Link} to={paths.plan(d.locked_by_deployment_id)} size="sm">Follow the plan</Anchor>}>
          It cannot be edited or deleted until the plan ends.
        </Notice>
      )}
      <Tabs value={tab} onChange={(v) => setParams(v && v !== 'overview' ? { tab: v } : {})} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="files">Files</Tabs.Tab>
          <Tabs.Tab value="log">Log</Tabs.Tab>
          <Tabs.Tab value="troubleshoot">Troubleshoot</Tabs.Tab>
          <Tabs.Tab value="intent">Intended settings</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="overview"><Overview d={d} /></Tabs.Panel>
        <Tabs.Panel value="intent"><IntentEditor key={d.updated_at} device={d} /></Tabs.Panel>
        <Tabs.Panel value="files"><ConfigWorkbench device={d} initialVersion={params.get('version')} /></Tabs.Panel>
        <Tabs.Panel value="log"><DeviceLog deviceId={d.id} /></Tabs.Panel>
        <Tabs.Panel value="troubleshoot"><TroubleshootPanel device={d} /></Tabs.Panel>
      </Tabs>
    </>
  );
}

/** A device whose management port UNDM switched off until its next power-on (D-107). */
function PortOff({ device }: { device: Device }) {
  const clear = useAction(() => api.clearPortOff(device.id), 'UNDM expects it at its address again');
  return (
    <Notice kind="settled" mb="md" title={`Port ${portOff(device)} off until its next power-on`}
      action={<Button size="xs" variant="default" loading={clear.isPending} onClick={() => clear.mutate(undefined)}>It was switched off and on</Button>}>
      UNDM switched off its management port so another device could take {device.management_address}. Nothing was saved on
      it: after it is switched off and on it answers at {device.management_address} again (UNDM notices on the next test).
    </Notice>
  );
}

import { Accordion, Alert, Anchor, Badge, Button, Card, Code, Group, SimpleGrid, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconEdit, IconLock, IconPlugConnected, IconTerminal2 } from '@tabler/icons-react';
import { useDisclosure } from '@mantine/hooks';
import type { ReactNode } from 'react';
import { Link, useParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { ConfigWorkbench } from '../features/configurations/ConfigWorkbench';
import { DiagnosticsButton } from '../features/devices/DiagnosticsButton';
import { EditDeviceModal } from '../features/devices/EditDeviceModal';
import { IntentEditor } from '../features/devices/IntentEditor';
import { useAction, useAudit, useCredentialRefs, useDevice, useDrivers, usePolicy, useProject } from '../hooks/queries';
import { api } from '../services/api';
import type { Device } from '../types/api';
import { auditActionLabel, capabilityLabel, driverLabel, factLabel, humanize, MAIN_FACTS, stateLabel } from '../services/labels';

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
  const refs = useCredentialRefs(d.project_id);
  const login = refs.data?.find((r) => r.id === d.credential_ref_id);
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
        <Title order={2} size="h5" mb="xs">What you entered</Title>
        <Table verticalSpacing={4}><Table.Tbody>
          <Row k="Model" v={`${d.manufacturer} ${d.model}`} />
          <Row k="Role" v={d.role} />
          <Row k="Address" v={<Text size="sm" ff="monospace">{d.management_address}</Text>} />
          <Row k="Login" v={login?.name ?? (d.credential_ref_id ? 'attached' : <Text span size="sm" c="orange">none yet: use Edit device</Text>)} />
          <Row k="Connects by" v={driverLabel(d.driver_id, drivers.data)} />
          <Row k="Setup" v={<StateBadge state={d.provisioning_status} />} />
          <Row k="Site / rack" v={[d.site, d.rack_location].filter(Boolean).join(' · ')} />
          <Row k="Tags" v={d.tags.map((t) => <Badge key={t} variant="outline" mr={4}>{t}</Badge>)} />
          <Row k="Notes" v={d.notes} />
        </Table.Tbody></Table>
        <Technical>
          <Table verticalSpacing={4}><Table.Tbody>
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
            <Title order={2} size="h5">What the device reported</Title>
            <Group gap="xs">
              <Button size="xs" variant="light" leftSection={<IconPlugConnected size={14} />} loading={op.isPending} onClick={() => op.mutate('check_reachability')}>Test connection</Button>
              <Button size="xs" variant="light" loading={op.isPending} onClick={() => op.mutate('get_facts')}>Retrieve information</Button>
              <Button size="xs" variant="light" loading={op.isPending} onClick={() => op.mutate('backup_configuration')}>Back up</Button>
            </Group>
          </Group>
          {facts ? (
            <Table verticalSpacing={4}><Table.Tbody>
              {main.map((k) => <Row key={k} k={factLabel(k)} v={String(flat[k])} />)}
              <Row k="Retrieved" v={fmtDate(d.facts_retrieved_at)} />
            </Table.Tbody></Table>
          ) : <Text size="sm" c="dimmed">Nothing retrieved yet. Use Retrieve information: the values on the left are what you entered, not what the device says.</Text>}
          {facts && (
            <Technical>
              {rest.length > 0 && (
                <Table verticalSpacing={4}><Table.Tbody>
                  {rest.map((k) => <Row key={k} k={factLabel(k)} v={String(flat[k])} />)}
                </Table.Tbody></Table>
              )}
              <RawOutput raw={extra.raw_output as Record<string, string> | undefined} />
              <Group mt="sm"><DiagnosticsButton device={d} /></Group>
            </Technical>
          )}
        </Card>
        <Card withBorder>
          <Title order={2} size="h5" mb="xs">Status</Title>
          <Table verticalSpacing={4}><Table.Tbody>
            <Row k="Status" v={<StateBadge state={d.deployment_status} />} />
            <Row k="Last connection" v={fmtDate(d.last_connection_at)} />
            <Row k="Last backup" v={fmtDate(d.last_backup_at)} />
            <Row k="Last plan" v={fmtDate(d.last_deployment_at)} />
          </Table.Tbody></Table>
        </Card>
        <Card withBorder>
          <Title order={2} size="h5" mb="xs">What UNDM can do with it</Title>
          <Group gap={6}>{d.capabilities.map((c) => <Badge key={c} variant="light" color="gray" tt="none">{capabilityLabel(c)}</Badge>)}</Group>
          <Text size="xs" c="dimmed" mt="xs">{d.environment === 'simulated'
            ? 'A simulated device: this says nothing about real hardware.'
            : 'What UNDM implements for this model. Real-device procedures stay marked experimental until tested on the bench.'}</Text>
        </Card>
      </Stack>
    </SimpleGrid>
  );
}

function Activity({ deviceId }: { deviceId: string }) {
  const audit = useAudit(deviceId);
  return (
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={520}>
        <Table verticalSpacing={6} horizontalSpacing="md">
          <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>By</Table.Th><Table.Th>Action</Table.Th><Table.Th>Result</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{(audit.data ?? []).map((a) => (
            <Table.Tr key={a.id}><Table.Td>{fmtDate(a.timestamp)}</Table.Td><Table.Td>{a.actor}</Table.Td><Table.Td>{auditActionLabel(a.action)}</Table.Td><Table.Td><StateBadge state={a.outcome} /></Table.Td></Table.Tr>
          ))}
          {audit.data?.length === 0 && <Table.Tr><Table.Td colSpan={4}><Text c="dimmed" ta="center" p="md">Nothing recorded for this device yet.</Text></Table.Td></Table.Tr>}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

/** Shown for platforms that have a console bootstrap procedure. */
function ConsoleBootstrapLink({ d }: { d: Device }) {
  const drivers = useDrivers();
  const platform = drivers.data?.find((x) => x.driver_id === d.driver_id)?.platform;
  if (platform !== 'aos_switch') return null;
  return <Button variant="default" component={Link} to={`/provisioning?device=${d.id}`} leftSection={<IconTerminal2 size={16} />}>Console bootstrap</Button>;
}

function RealDeviceNotice({ d }: { d: Device }) {
  const drivers = useDrivers();
  const policy = usePolicy();
  const driver = drivers.data?.find((x) => x.driver_id === d.driver_id);
  if (!driver || driver.simulated) return null;
  const writes = policy.data?.enable_real_device_writes;
  return (
    <Alert color={d.environment === 'production' ? 'red' : 'orange'} icon={<IconAlertTriangle size={18} />} mb="md"
      title={driver.maturity === 'experimental' ? 'Real device · procedures still being proven on the bench' : 'Real device'}>
      <Text size="sm">
        UNDM connects to this device over {driver.transport.toUpperCase()}.{' '}
        {d.environment === 'production'
          ? 'Production devices are blocked: UNDM is for staging on the bench.'
          : writes ? 'Real-device changes are ON: approved plans may change this device.'
            : 'Real-device changes are OFF: you can read and back up this device, and run dry runs. Turn changes on in Settings → Safety.'}
        {d.environment !== 'production' && driver.capabilities.includes('supports_firmware_upgrade') && (policy.data?.enable_real_device_firmware && writes
          ? ' Firmware changes are ON (approved plan and time window needed).'
          : ' Firmware changes are OFF (Settings → Safety).')}
        {!d.credential_ref_id && ' No login chosen yet: use Edit device.'}
      </Text>
    </Alert>
  );
}

export function DeviceDetailPage() {
  const { deviceId = '' } = useParams();
  const device = useDevice(deviceId);
  const system = useProject(device.data?.project_id ?? '');
  const [editing, { open: openEdit, close: closeEdit }] = useDisclosure();
  if (!device.data) return <QueryState isLoading={device.isLoading} error={device.error} />;
  const d = device.data;
  return (
    <>
      <PageHeader title={d.name}
        description={<Group gap="xs" component="span"><EnvironmentBadge env={d.environment} /><span>{d.manufacturer} {d.model} · <Anchor component={Link} to={`/projects/${d.project_id}`} size="sm">{system.data?.name ?? 'system'}</Anchor></span></Group>}
        actions={<>
          <ConsoleBootstrapLink d={d} />
          <Button variant="default" leftSection={<IconEdit size={16} />} onClick={openEdit} disabled={!!d.locked_by_deployment_id}>Edit device</Button>
        </>} />
      <RealDeviceNotice d={d} />
      {editing && <EditDeviceModal device={d} opened={editing} onClose={closeEdit} />}
      {d.locked_by_deployment_id && (
        <Alert color="orange" icon={<IconLock size={18} />} mb="md">
          Locked by a running deployment. <Anchor component={Link} to={`/deployments/${d.locked_by_deployment_id}`}>View deployment</Anchor>
        </Alert>
      )}
      <Tabs defaultValue="overview" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="intent">Intent</Tabs.Tab>
          <Tabs.Tab value="configs">Configurations</Tabs.Tab>
          <Tabs.Tab value="activity">Activity</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="overview"><Overview d={d} /></Tabs.Panel>
        <Tabs.Panel value="intent"><IntentEditor key={d.updated_at} device={d} /></Tabs.Panel>
        <Tabs.Panel value="configs"><ConfigWorkbench device={d} /></Tabs.Panel>
        <Tabs.Panel value="activity"><Activity deviceId={d.id} /></Tabs.Panel>
      </Tabs>
    </>
  );
}

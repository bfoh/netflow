import { Accordion, Alert, Anchor, Badge, Button, Card, Code, Group, SimpleGrid, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconEdit, IconLock, IconPlugConnected, IconTerminal2 } from '@tabler/icons-react';
import { useDisclosure } from '@mantine/hooks';
import { Link, useParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { ConfigWorkbench } from '../features/configurations/ConfigWorkbench';
import { DiagnosticsButton } from '../features/devices/DiagnosticsButton';
import { EditDeviceModal } from '../features/devices/EditDeviceModal';
import { IntentEditor } from '../features/devices/IntentEditor';
import { useAction, useAudit, useDevice, useDrivers, usePolicy } from '../hooks/queries';
import { api } from '../services/api';
import type { Device } from '../types/api';

function Row({ k, v }: { k: string; v: React.ReactNode }) {
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

function Overview({ d }: { d: Device }) {
  const op = useAction((o: string) => api.runOperation(d.id, o), (r) => `Result: ${r.status}${r.message ? ` — ${r.message}` : ''}`);
  const facts = d.observed_facts as Record<string, unknown> | null;
  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      <Card withBorder>
        <Title order={5} mb="xs">Declared (entered by users)</Title>
        <Table verticalSpacing={4}><Table.Tbody>
          <Row k="Manufacturer / family" v={`${d.manufacturer} ${d.product_family}`} />
          <Row k="Model / HW revision" v={`${d.model} ${d.hardware_revision}`} />
          <Row k="Category / role" v={`${d.category} · ${d.role || 'no role'}`} />
          <Row k="OS / firmware" v={`${d.os_family} ${d.firmware_version}`} />
          <Row k="Management" v={<Text size="sm" ff="monospace">{d.management_address} ({d.management_protocol}{d.management_port ? `:${d.management_port}` : ''})</Text>} />
          <Row k="Management VRF" v={d.management_vrf} />
          <Row k="Site / rack" v={`${d.site} ${d.rack_location}`} />
          <Row k="Driver" v={<code>{d.driver_id}</code>} />
          <Row k="Credential" v={d.credential_ref_id ? 'attached' : '—'} />
          <Row k="Provisioning status" v={<StateBadge state={d.provisioning_status} />} />
          <Row k="Tags" v={d.tags.map((t) => <Badge key={t} variant="outline" mr={4}>{t}</Badge>)} />
          <Row k="Notes" v={d.notes} />
        </Table.Tbody></Table>
      </Card>
      <Stack>
        <Card withBorder>
          <Group justify="space-between" mb="xs">
            <Title order={5}>Observed (retrieved from the device)</Title>
            <Group gap="xs">
              <Button size="xs" variant="light" leftSection={<IconPlugConnected size={14} />} loading={op.isPending} onClick={() => op.mutate('check_reachability')}>Test connection</Button>
              <Button size="xs" variant="light" loading={op.isPending} onClick={() => op.mutate('get_facts')}>Retrieve information</Button>
              <Button size="xs" variant="light" loading={op.isPending} onClick={() => op.mutate('backup_configuration')}>Back up</Button>
            </Group>
          </Group>
          {facts ? (
            <Table verticalSpacing={4}><Table.Tbody>
              {Object.entries(facts).filter(([k]) => k !== 'extra').map(([k, v]) => <Row key={k} k={k} v={String(v ?? '—')} />)}
              {Object.entries((facts.extra ?? {}) as Record<string, unknown>)
                .filter(([k, v]) => k !== 'raw_output' && v !== null && typeof v !== 'object')
                .map(([k, v]) => <Row key={k} k={k} v={String(v)} />)}
              <Row k="Retrieved" v={fmtDate(d.facts_retrieved_at)} />
            </Table.Tbody></Table>
          ) : <Text size="sm" c="dimmed">Nothing retrieved yet. Values above are not verified against the device.</Text>}
          {facts && <RawOutput raw={(facts.extra as { raw_output?: Record<string, string> } | undefined)?.raw_output} />}
          {facts && <Group mt="sm"><DiagnosticsButton device={d} /></Group>}
        </Card>
        <Card withBorder>
          <Title order={5} mb="xs">Status</Title>
          <Table verticalSpacing={4}><Table.Tbody>
            <Row k="Deployment status" v={<StateBadge state={d.deployment_status} />} />
            <Row k="Last connection" v={fmtDate(d.last_connection_at)} />
            <Row k="Last backup" v={fmtDate(d.last_backup_at)} />
            <Row k="Last deployment" v={fmtDate(d.last_deployment_at)} />
          </Table.Tbody></Table>
        </Card>
        <Card withBorder>
          <Title order={5} mb="xs">Driver capabilities</Title>
          <Group gap={6}>{d.capabilities.map((c) => <Badge key={c} variant="light" color="gray">{c.replace('supports_', '').replaceAll('_', ' ')}</Badge>)}</Group>
          <Text size="xs" c="dimmed" mt="xs">Capabilities of the simulation profile; not a statement about real hardware.</Text>
        </Card>
      </Stack>
    </SimpleGrid>
  );
}

function Activity({ deviceId }: { deviceId: string }) {
  const audit = useAudit(deviceId);
  return (
    <Card withBorder padding={0}>
      <Table verticalSpacing={6} horizontalSpacing="md">
        <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>Actor</Table.Th><Table.Th>Action</Table.Th><Table.Th>Outcome</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{(audit.data ?? []).map((a) => (
          <Table.Tr key={a.id}><Table.Td>{fmtDate(a.timestamp)}</Table.Td><Table.Td>{a.actor}</Table.Td><Table.Td>{a.action}</Table.Td><Table.Td><StateBadge state={a.outcome} /></Table.Td></Table.Tr>
        ))}</Table.Tbody>
      </Table>
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
      title={`Real device · ${driver.maturity} driver`}>
      <Text size="sm">
        UNDM connects to this device over {driver.transport.toUpperCase()}.{' '}
        {d.environment === 'production'
          ? 'Production devices are blocked unless UNDM_ALLOW_PRODUCTION_READ_ONLY / UNDM_ALLOW_PRODUCTION_DEPLOYMENTS are enabled.'
          : writes ? 'Configuration changes to lab devices are ENABLED on this server (through approved deployments only).'
            : 'Read-only actions and dry runs are allowed. Configuration changes are disabled on this server (UNDM_ENABLE_REAL_DEVICE_WRITES).'}
        {!d.credential_ref_id && ' No credential attached yet: use Edit device.'}
      </Text>
    </Alert>
  );
}

export function DeviceDetailPage() {
  const { deviceId = '' } = useParams();
  const device = useDevice(deviceId);
  const [editing, { open: openEdit, close: closeEdit }] = useDisclosure();
  if (!device.data) return <QueryState isLoading={device.isLoading} error={device.error} />;
  const d = device.data;
  return (
    <>
      <PageHeader title={d.name}
        description={<Group gap="xs" component="span"><EnvironmentBadge env={d.environment} /><span>{d.manufacturer} {d.model} · <Anchor component={Link} to={`/projects/${d.project_id}`} size="sm">project</Anchor></span></Group>}
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

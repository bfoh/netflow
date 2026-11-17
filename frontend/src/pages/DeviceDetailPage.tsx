import { Alert, Anchor, Badge, Button, Card, Group, SimpleGrid, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import { Link, useParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { ConfigWorkbench } from '../features/configurations/ConfigWorkbench';
import { IntentEditor } from '../features/devices/IntentEditor';
import { useAction, useAudit, useDevice } from '../hooks/queries';
import { api } from '../services/api';
import type { Device } from '../types/api';

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <Table.Tr><Table.Td c="dimmed" w={190}>{k}</Table.Td><Table.Td>{v || '—'}</Table.Td></Table.Tr>;
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
              <Button size="xs" variant="light" loading={op.isPending} onClick={() => op.mutate('get_facts')}>Retrieve information</Button>
              <Button size="xs" variant="light" loading={op.isPending} onClick={() => op.mutate('backup_configuration')}>Back up</Button>
            </Group>
          </Group>
          {facts ? (
            <Table verticalSpacing={4}><Table.Tbody>
              {Object.entries(facts).map(([k, v]) => <Row key={k} k={k} v={typeof v === 'object' ? JSON.stringify(v) : String(v)} />)}
              <Row k="Retrieved" v={fmtDate(d.facts_retrieved_at)} />
            </Table.Tbody></Table>
          ) : <Text size="sm" c="dimmed">Nothing retrieved yet. Values above are not verified against the device.</Text>}
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

export function DeviceDetailPage() {
  const { deviceId = '' } = useParams();
  const device = useDevice(deviceId);
  if (!device.data) return <QueryState isLoading={device.isLoading} error={device.error} />;
  const d = device.data;
  return (
    <>
      <PageHeader title={d.name}
        description={<Group gap="xs" component="span"><EnvironmentBadge env={d.environment} /><span>{d.manufacturer} {d.model} · <Anchor component={Link} to={`/projects/${d.project_id}`} size="sm">project</Anchor></span></Group>} />
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

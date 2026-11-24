import { Anchor, Card, Group, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

import { StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate, planKind } from '../services/format';
import { useAllDeployments, useAllDevices, useProjects } from '../hooks/queries';

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <Card withBorder padding="md">
      <Text size="xs" tt="uppercase" fw={600} c="dimmed">{label}</Text>
      <Text fz={28} fw={700}>{value}</Text>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </Card>
  );
}

function countBy<T>(items: T[], key: (t: T) => string): [string, number][] {
  const m = new Map<string, number>();
  items.forEach((i) => m.set(key(i), (m.get(key(i)) ?? 0) + 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

function Breakdown({ title, rows }: { title: string; rows: [string, number][] }) {
  return (
    <Card withBorder>
      <Title order={5} mb="xs">{title}</Title>
      {rows.length === 0 ? <Text c="dimmed" size="sm">No devices yet.</Text> : (
        <Stack gap={4}>
          {rows.map(([k, v]) => (
            <Group key={k} justify="space-between"><Text size="sm">{k}</Text><Text size="sm" fw={600}>{v}</Text></Group>
          ))}
        </Stack>
      )}
    </Card>
  );
}

const FAILED = new Set(['failed', 'recovery_required', 'rolled_back']);

export function DashboardPage() {
  const devices = useAllDevices();
  const projects = useProjects();
  const deployments = useAllDeployments();
  const d = devices.data ?? [];
  const deps = deployments.data ?? [];
  const projectName = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const contacted = d.filter((x) => x.last_connection_at).length;

  return (
    <>
      <PageHeader title="Dashboard" description="Overview of projects, network elements and deployment activity." />
      <QueryState isLoading={devices.isLoading} error={devices.error ?? projects.error ?? deployments.error} />
      <SimpleGrid cols={{ base: 2, md: 3, lg: 6 }} mb="lg">
        <Stat label="Projects" value={projects.data?.length ?? 0} />
        <Stat label="Network elements" value={d.length} />
        <Stat label="Contacted" value={contacted} hint="at least one successful connection" />
        <Stat label="Never contacted" value={d.length - contacted} />
        <Stat label="Pending approvals" value={deps.filter((x) => x.state === 'awaiting_approval').length} />
        <Stat label="Failed / recovery" value={deps.filter((x) => FAILED.has(x.state)).length} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 3 }} mb="lg">
        <Breakdown title="Devices by vendor" rows={countBy(d, (x) => x.manufacturer)} />
        <Breakdown title="Devices by category" rows={countBy(d, (x) => x.category)} />
        <Breakdown title="Devices by environment" rows={countBy(d, (x) => x.environment)} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <Card withBorder>
          <Title order={5} mb="xs">Recent deployments</Title>
          {deps.length === 0 ? <Text c="dimmed" size="sm">No deployments yet.</Text> : (
            <Table.ScrollContainer minWidth={420}>
              <Table verticalSpacing={6}>
                <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>Project</Table.Th><Table.Th>Type</Table.Th><Table.Th>State</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {deps.slice(0, 8).map((x) => (
                    <Table.Tr key={x.id}>
                      <Table.Td><Anchor component={Link} to={`/deployments/${x.id}`} size="sm">{fmtDate(x.created_at)}</Anchor></Table.Td>
                      <Table.Td>{projectName.get(x.project_id) ?? '—'}</Table.Td>
                      <Table.Td>{planKind(x)}</Table.Td>
                      <Table.Td><StateBadge state={x.state} /></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Card>
        <Card withBorder>
          <Title order={5} mb="xs">Projects</Title>
          {(projects.data ?? []).length === 0 ? <Text c="dimmed" size="sm">No projects yet. <Anchor component={Link} to="/projects">Create one</Anchor>.</Text> : (
            <Stack gap={6}>
              {(projects.data ?? []).map((p) => (
                <Group key={p.id} justify="space-between">
                  <Anchor component={Link} to={`/projects/${p.id}`}>{p.name}</Anchor>
                  <Text size="sm" c="dimmed">{d.filter((x) => x.project_id === p.id).length} devices</Text>
                </Group>
              ))}
            </Stack>
          )}
          <Text size="xs" c="dimmed" mt="md">Firmware status: not tracked yet (Firmware Manager is planned for Phase 7).</Text>
        </Card>
      </SimpleGrid>
    </>
  );
}

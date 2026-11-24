import { Anchor, Badge, Button, Card, Group, List, SimpleGrid, Stack, Table, Text, ThemeIcon, Title } from '@mantine/core';
import type { ReactNode } from 'react';
import { IconAlertTriangle, IconCircleCheck, IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';

import { StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { planKind } from '../services/labels';
import { useAllDeployments, useAllDevices, useProjects } from '../hooks/queries';
import type { DeploymentSummary } from '../types/api';

function Stat({ label, value, hint, to }: { label: string; value: number | string; hint?: string; to: string }) {
  return (
    <Card withBorder padding="md" component={Link} to={to}>
      <Text size="xs" tt="uppercase" fw={600} c="dimmed">{label}</Text>
      <Text fz={28} fw={700}>{value}</Text>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </Card>
  );
}

const ATTENTION = new Set(['failed', 'recovery_required', 'rolled_back']);
const RUNNING = new Set(['validating', 'preflight', 'backing_up', 'deploying', 'verifying', 'recovering']);

/** What the person should do next with a plan, or null when nothing is waiting. */
function nextAction(d: DeploymentSummary): string | null {
  if (d.state === 'awaiting_approval') return 'Read the preview and approve it';
  if (d.state === 'ready') return 'Approved: run it when the devices are cabled';
  if (RUNNING.has(d.state)) return 'Running now: follow its progress';
  if (d.state === 'recovery_required') return 'Check the device: it may be half-changed';
  return null;
}

function Step({ done, children }: { done: boolean; children: ReactNode }) {
  return (
    <List.Item icon={<ThemeIcon size={20} radius="xl" color={done ? 'teal' : 'gray'} variant={done ? 'filled' : 'light'}>
      {done ? <IconCircleCheck size={14} /> : <span />}</ThemeIcon>}>{children}</List.Item>
  );
}

/** First steps, shown while there is nothing to stage yet. */
function GettingStarted({ hasSystems, hasDevices }: { hasSystems: boolean; hasDevices: boolean }) {
  return (
    <Card withBorder mb="lg">
      <Title order={2} size="h3" mb="xs">Getting started</Title>
      <Text size="sm" c="dimmed" mb="sm">Staging a system takes four steps. UNDM checks every change and asks for approval before it touches a device.</Text>
      <List spacing="xs" size="sm" center>
        <Step done={hasSystems}><Anchor component={Link} to="/projects">Create a system</Anchor>: the set of devices you stage together.</Step>
        <Step done={hasDevices}>Add its devices on the system page (model, address, login).</Step>
        <Step done={false}>Add the files from your team (<Anchor component={Link} to="/configurations">Files</Anchor>) and approved images (<Anchor component={Link} to="/firmware">Firmware</Anchor>).</Step>
        <Step done={false}>Make a plan (<Anchor component={Link} to="/deployments">Plans</Anchor>), approve it and run it.</Step>
      </List>
    </Card>
  );
}

export function DashboardPage() {
  const devices = useAllDevices();
  const projects = useProjects();
  const deployments = useAllDeployments();
  const d = devices.data ?? [];
  const deps = deployments.data ?? [];
  const systems = projects.data ?? [];
  const projectName = new Map(systems.map((p) => [p.id, p.name]));
  const waiting = deps.filter((x) => nextAction(x));
  const attention = deps.filter((x) => ATTENTION.has(x.state));
  const loaded = !devices.isLoading && !projects.isLoading;

  return (
    <>
      <PageHeader title="Home" description="Your systems, the plans waiting for you and what ran last."
        actions={<Button component={Link} to="/projects" leftSection={<IconPlus size={16} />} variant="light">New system</Button>} />
      <QueryState isLoading={devices.isLoading} error={devices.error ?? projects.error ?? deployments.error} />
      {loaded && (systems.length === 0 || d.length === 0) && <GettingStarted hasSystems={systems.length > 0} hasDevices={d.length > 0} />}
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
        <Stat label="Systems" value={systems.length} to="/projects" />
        <Stat label="Devices" value={d.length} hint={`${d.filter((x) => x.last_connection_at).length} reached at least once`} to="/devices" />
        <Stat label="Waiting for you" value={waiting.length} hint="to approve, run or check" to="/deployments" />
        <Stat label="Did not finish" value={attention.length} hint="failed, undone or needs attention" to="/deployments" />
      </SimpleGrid>
      {waiting.length > 0 && (
        <Card withBorder mb="lg">
          <Title order={2} size="h3" mb="xs">Waiting for you</Title>
          <Stack gap={6}>
            {waiting.slice(0, 8).map((x) => (
              <Group key={x.id} justify="space-between" wrap="nowrap">
                <Group gap="xs" wrap="nowrap">
                  {x.state === 'recovery_required' && <IconAlertTriangle size={16} color="var(--mantine-color-red-6)" aria-label="Needs attention" />}
                  <Anchor component={Link} to={`/deployments/${x.id}`} size="sm">{planKind(x)}</Anchor>
                  <Text size="sm" c="dimmed">{projectName.get(x.project_id) ?? ''}</Text>
                </Group>
                <Group gap="xs" wrap="nowrap">
                  <Text size="sm" visibleFrom="sm">{nextAction(x)}</Text>
                  <StateBadge state={x.state} />
                </Group>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <Card withBorder>
          <Title order={2} size="h3" mb="xs">Recent plans</Title>
          {deps.length === 0 ? <Text c="dimmed" size="sm">No plans yet. A plan is one approved piece of work on devices, such as loading a file or upgrading firmware.</Text> : (
            <Table.ScrollContainer minWidth={420}>
              <Table verticalSpacing={6}>
                <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>System</Table.Th><Table.Th>Type</Table.Th><Table.Th>Status</Table.Th></Table.Tr></Table.Thead>
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
          <Title order={2} size="h3" mb="xs">Systems</Title>
          {systems.length === 0 ? <Text c="dimmed" size="sm">No systems yet. <Anchor component={Link} to="/projects">Create one</Anchor>.</Text> : (
            <Stack gap={6}>
              {systems.map((p) => {
                const mine = d.filter((x) => x.project_id === p.id);
                const done = mine.filter((x) => x.deployment_status === 'in_sync').length;
                return (
                  <Group key={p.id} justify="space-between" wrap="nowrap">
                    <Anchor component={Link} to={`/projects/${p.id}`}>{p.name}</Anchor>
                    <Group gap="xs" wrap="nowrap">
                      <Text size="sm" c="dimmed">{mine.length} {mine.length === 1 ? 'device' : 'devices'}</Text>
                      {mine.length > 0 && <Badge variant="light" color={done === mine.length ? 'teal' : 'gray'} radius="sm" tt="none">{done} of {mine.length} up to date</Badge>}
                    </Group>
                  </Group>
                );
              })}
            </Stack>
          )}
        </Card>
      </SimpleGrid>
    </>
  );
}

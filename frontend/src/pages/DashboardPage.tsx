import { StagedBadge } from '../features/systems/StagedBadge';
import { Anchor, Button, Card, Group, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconListCheck } from '@tabler/icons-react';
import { Link } from 'react-router';

import { StateBadge, Tag } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { SetupChecklist } from '../features/home/SetupChecklist';
import { lastSystem, placeOf } from '../features/stage/wizardMemory';
import { PlanStatus } from '../features/plans/AttentionBadge';
import { fmtDate } from '../services/format';
import { planKind } from '../services/labels';
import { useAllDeployments, useAllDevices, useProjects } from '../hooks/queries';
import type { DeploymentSummary, Project } from '../types/api';
import { paths } from '../paths';

function Stat({ label, value, hint, to }: { label: string; value: number | string; hint?: string; to: string }) {
  return (
    <Card withBorder padding="md" component={Link} to={to}>
      <Text size="xs" tt="uppercase" fw={600} c="dimmed">{label}</Text>
      <Text fz={28} fw={700}>{value}</Text>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </Card>
  );
}

const RUNNING = new Set(['validating', 'preflight', 'backing_up', 'deploying', 'verifying', 'recovering']);

/** What the person should do next with a plan, or null when nothing is waiting. */
function nextAction(d: DeploymentSummary): string | null {
  if (d.state === 'awaiting_approval') return 'Read the preview and approve it';
  if (d.state === 'ready') return 'Approved: run it when the devices are cabled';
  if (RUNNING.has(d.state)) return 'Running now: follow its progress';
  // Until a later plan succeeded on its device(s) or a person marked it checked (D-088).
  if (d.state === 'recovery_required' && d.needs_attention) return 'Check the device: it may be half-changed';
  return null;
}

/** The system last worked on in Stage a system, while it is not finished (D-120). */
function ContinueStaging({ systems }: { systems: Project[] }) {
  const last = lastSystem();
  const p = systems.find((x) => x.id === last && !x.staged_at);
  if (!p) return null;
  const step = placeOf(p.id)?.step ?? 0;
  return (
    <Card mb="lg">
      <Group justify="space-between" wrap="wrap">
        <div>
          <Title order={2}>Continue staging {p.name}</Title>
          <Text size="sm" c="dimmed">Where you left it: step {step + 1} of 5.</Text>
        </div>
        <Button component={Link} to={paths.stage(p.id, step)} leftSection={<IconListCheck size={16} />}>Continue</Button>
      </Group>
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
  const attention = deps.filter((x) => x.needs_attention);
  const loaded = !devices.isLoading && !projects.isLoading;

  return (
    <>
      <PageHeader title="Home" description="Your systems, the plans waiting for you and what ran last."
        primary={<Button component={Link} to={paths.stage()} leftSection={<IconListCheck size={16} />}>Stage a system</Button>} />
      <QueryState isLoading={devices.isLoading} error={devices.error ?? projects.error ?? deployments.error} />
      {loaded && <ContinueStaging systems={systems} />}
      <SetupChecklist />
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
        <Stat label="Systems" value={systems.length} to={paths.systems} />
        <Stat label="Devices" value={d.length} hint={`${d.filter((x) => x.last_connection_at).length} reached at least once`} to={paths.devices} />
        <Stat label="Waiting for you" value={waiting.length} hint="to approve, run or check" to={paths.plans} />
        <Stat label="Needs attention" value={attention.length} hint="a device may be half-changed" to={paths.plans} />
      </SimpleGrid>
      {waiting.length > 0 && (
        <Card withBorder mb="lg">
          <Title order={2} mb="xs">Waiting for you</Title>
          <Stack gap={6}>
            {waiting.slice(0, 8).map((x) => (
              <Group key={x.id} justify="space-between" wrap="nowrap">
                <Group gap="xs" wrap="nowrap">
                  {x.state === 'recovery_required' && <IconAlertTriangle size={16} color="var(--mantine-color-red-6)" aria-label="Needs attention" />}
                  <Anchor component={Link} to={paths.plan(x.id)} size="sm">{planKind(x)}</Anchor>
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
      <SimpleGrid cols={{ base: 1, xl: 2 }}>
        <Card withBorder>
          <Title order={2} mb="xs">Recent plans</Title>
          {deps.length === 0 ? <Text c="dimmed" size="sm">No plans yet. A plan is one approved piece of work on devices, such as loading a file or upgrading firmware.</Text> : (
            <Table.ScrollContainer minWidth={420}>
              <Table aria-label="Recent plans" verticalSpacing={6}>
                <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>System</Table.Th><Table.Th>Type</Table.Th><Table.Th>Status</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {deps.slice(0, 8).map((x) => (
                    <Table.Tr key={x.id}>
                      <Table.Td style={{ whiteSpace: 'nowrap' }}><Anchor component={Link} to={paths.plan(x.id)} size="sm">{fmtDate(x.created_at)}</Anchor></Table.Td>
                      <Table.Td>{projectName.get(x.project_id) ?? '—'}</Table.Td>
                      <Table.Td>{planKind(x)}</Table.Td>
                      <Table.Td><PlanStatus d={x} /></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Card>
        <Card withBorder>
          <Title order={2} mb="xs">Systems</Title>
          {systems.length === 0 ? <Text c="dimmed" size="sm">No systems yet. <Anchor component={Link} to={paths.systems}>Create one</Anchor>.</Text> : (
            <Stack gap={6}>
              {systems.map((p) => {
                const mine = d.filter((x) => x.project_id === p.id);
                const done = mine.filter((x) => x.deployment_status === 'in_sync').length;
                return (
                  <Group key={p.id} justify="space-between" wrap="nowrap">
                    <Anchor component={Link} to={paths.system(p.id)}>{p.name}</Anchor>
                    <Group gap="xs" wrap="nowrap">
                      <Text size="sm" c="dimmed">{mine.length} {mine.length === 1 ? 'device' : 'devices'}</Text>
                      {p.staged_at ? <StagedBadge project={p} />
                        : mine.length > 0 && <Tag tone={done === mine.length ? 'success' : 'neutral'}>{done} of {mine.length} up to date</Tag>}
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

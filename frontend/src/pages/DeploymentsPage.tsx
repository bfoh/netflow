import { Alert, Anchor, Button, Card, Checkbox, Group, SegmentedControl, Select, Stack, Switch, Table, Text, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { useAction, useAllDeployments, useProjectDevices, useProjects } from '../hooks/queries';
import { api } from '../services/api';

function NewPlan({ projectId, preselected }: { projectId: string; preselected: string[] }) {
  const devices = useProjectDevices(projectId);
  const [sel, setSel] = useState<string[]>(preselected);
  const [dryRun, setDryRun] = useState(false);
  const [mode, setMode] = useState('merge');
  const navigate = useNavigate();
  const create = useAction(() => api.createDeployment(projectId, { device_ids: sel, dry_run: dryRun, apply_mode: mode }),
    (d) => `Plan created: ${d.state.replaceAll('_', ' ')}`);

  return (
    <Card withBorder>
      <Title order={4} mb="xs">New deployment plan</Title>
      <Text size="sm" c="dimmed" mb="md">
        The latest generated configuration of each selected device is validated and previewed against the device.
        Live plans then need approval before execution; dry runs only read from devices.
      </Text>
      <QueryState isLoading={devices.isLoading} error={devices.error} />
      <Table verticalSpacing={4} mb="md">
        <Table.Tbody>
          {(devices.data ?? []).map((d) => (
            <Table.Tr key={d.id}>
              <Table.Td w={36}><Checkbox aria-label={`Include ${d.name}`} checked={sel.includes(d.id)}
                onChange={() => setSel((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id]))} /></Table.Td>
              <Table.Td>{d.name}</Table.Td><Table.Td>{d.manufacturer} {d.model}</Table.Td>
              <Table.Td><EnvironmentBadge env={d.environment} /></Table.Td><Table.Td><StateBadge state={d.deployment_status} /></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Group mb="md" wrap="wrap">
        <Switch label="Dry run (read-only, no approval needed)" checked={dryRun} onChange={(e) => setDryRun(e.currentTarget.checked)} />
        <Group gap="xs"><Text size="sm">Apply mode</Text>
          <SegmentedControl size="xs" value={mode} onChange={setMode} data={[{ value: 'merge', label: 'Merge' }, { value: 'replace', label: 'Replace' }]} /></Group>
      </Group>
      {mode === 'replace' && (
        <Alert color="yellow" icon={<IconInfoCircle size={16} />} mb="md">
          Replace makes the running configuration equal to the generated one, removing everything else. Drivers that cannot replace are rejected at validation.
        </Alert>
      )}
      <Button disabled={sel.length === 0} loading={create.isPending}
        onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(`/deployments/${d.id}`) })}>
        Validate and preview
      </Button>
    </Card>
  );
}

export function DeploymentsPage() {
  const [params, setParams] = useSearchParams();
  const projects = useProjects();
  const all = useAllDeployments();
  const projectId = params.get('project');
  const preselected = (params.get('devices') ?? '').split(',').filter(Boolean);
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));

  return (
    <>
      <PageHeader title="Deployment Center" description="Plan, approve, execute and inspect configuration deployments." />
      <Stack>
        <Card withBorder>
          <Select label="Project for a new plan" placeholder="Choose a project" maw={420}
            data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
            value={projectId} onChange={(v) => setParams(v ? { project: v } : {})} />
        </Card>
        {projectId && <NewPlan key={projectId + preselected.join()} projectId={projectId} preselected={preselected} />}
        <Card withBorder padding={0}>
          <Title order={5} p="md" pb={0}>All deployments</Title>
          <QueryState isLoading={all.isLoading} error={all.error} />
          <Table.ScrollContainer minWidth={640}>
            <Table verticalSpacing="xs" horizontalSpacing="md" highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>Project</Table.Th><Table.Th>Type</Table.Th><Table.Th>Created by</Table.Th><Table.Th>Approved by</Table.Th><Table.Th>State</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(all.data ?? []).map((d) => (
                  <Table.Tr key={d.id}>
                    <Table.Td><Anchor component={Link} to={`/deployments/${d.id}`} size="sm">{fmtDate(d.created_at)}</Anchor></Table.Td>
                    <Table.Td>{names.get(d.project_id) ?? '—'}</Table.Td>
                    <Table.Td>{d.dry_run ? 'dry run' : 'live'} · {d.apply_mode}</Table.Td>
                    <Table.Td>{d.created_by}</Table.Td><Table.Td>{d.approved_by ?? '—'}</Table.Td>
                    <Table.Td><StateBadge state={d.state} /></Table.Td>
                  </Table.Tr>
                ))}
                {all.data?.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" p="md">No deployments yet.</Text></Table.Td></Table.Tr>}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      </Stack>
    </>
  );
}

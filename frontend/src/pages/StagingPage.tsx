import { Alert, Anchor, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconPlayerPlay, IconPlayerStop, IconShieldCheck } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { RUNNING_STATES, useAction, useStaging } from '../hooks/queries';
import { api } from '../services/api';
import { fmtDate } from '../services/format';
import type { Deployment } from '../types/api';

function stepTitle(step: Deployment): string {
  const what = step.kind === 'first_login'
    ? 'first login: sets the device\'s login when the new unit asks for a new password'
    : step.apply_mode === 'replace'
      ? 'base file (replace): the device fetches it, restarts and comes back with it'
      : 'site file (merge): sent statement by statement once the steps before it have succeeded';
  return `Step ${step.staging_step} · ${what}`;
}

function StepCard({ step }: { step: Deployment }) {
  const events = step.events.slice(-6);
  return (
    <Card withBorder>
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Text fw={600} size="sm">{stepTitle(step)}</Text>
        <StateBadge state={step.state} />
      </Group>
      <Stack gap={2}>
        {events.map((e) => (
          <Text key={e.seq} size="xs" c={e.status === 'error' ? 'red' : e.status === 'warning' ? 'orange' : 'dimmed'}>
            {fmtDate(e.timestamp)} · {e.stage} — {e.message}
          </Text>
        ))}
      </Stack>
      <Anchor component={Link} to={`/deployments/${step.id}`} size="sm" mt="xs">Open this step (all events, configuration after loading)</Anchor>
    </Card>
  );
}

export function StagingPage() {
  const { stagingId = '' } = useParams();
  const [started, setStarted] = useState(false);
  const plan = useStaging(stagingId, started);
  const steps = plan.data?.steps ?? [];
  const approve = useAction(() => api.approveStaging(stagingId), 'Staging plan approved');
  const execute = useAction(() => api.executeStaging(stagingId), 'Staging plan started');
  const stop = useAction(() => api.stopStaging(stagingId), 'Stop requested: the running step ends at its next safe point');
  const running = steps.some((s) => RUNNING_STATES.has(s.state));
  const pending = steps.filter((s) => s.state !== 'succeeded');
  const canApprove = steps.some((s) => s.state === 'awaiting_approval');
  const canRun = !running && pending.length > 0 && pending.every((s) => s.state === 'ready');
  const done = steps.length > 0 && pending.length === 0;
  const ended = !running && pending.some((s) => ['failed', 'recovery_required', 'rolled_back', 'cancelled'].includes(s.state));

  return (
    <>
      <PageHeader title="Staging plan · base file, then site file"
        description={steps[0] ? `Created by ${steps[0].created_by} · ${fmtDate(steps[0].created_at)}${steps[0].approved_by ? ` · approved by ${steps[0].approved_by}` : ''}` : ''}
        actions={<Group gap="xs">
          {canApprove && <Button leftSection={<IconShieldCheck size={16} />} loading={approve.isPending}
            onClick={() => approve.mutate(undefined)}>{steps.length > 2 ? 'Approve all steps' : 'Approve both steps'}</Button>}
          {canRun && <Button leftSection={<IconPlayerPlay size={16} />} loading={execute.isPending}
            onClick={() => execute.mutate(undefined, { onSuccess: () => setStarted(true) })}>Execute</Button>}
          {running && <Button color="red" variant="light" leftSection={<IconPlayerStop size={16} />} loading={stop.isPending}
            onClick={() => stop.mutate(undefined)}>Stop</Button>}
        </Group>} />
      <QueryState isLoading={plan.isLoading} error={plan.error} />
      <Stack>
        {done && <Alert color="teal" icon={<IconCheck size={18} />} title="Both steps succeeded">
          The base file was restored and the site file loaded; each step saved a revision on the device.</Alert>}
        {ended && <Alert color="red" icon={<IconAlertTriangle size={18} />} title="The plan did not complete">
          A step did not succeed, so the steps after it did not run. Open the step for its events. To start again, create a new
          staging plan: it restores the base file first, so the site file never lands on an earlier one.</Alert>}
        {running && <Alert color="blue" title="In progress">
          The run continues on the server even if you leave this page. The base file restarts the device (several minutes); each step starts
          by itself when the one before it has succeeded. Stop ends the running step at its next safe point, and the later steps do not run.</Alert>}
        {!running && !done && !ended && <Text size="sm" c="dimmed">
          One approval covers both steps. Step 2 is previewed when it runs, after the base file is on the device; running it on its
          own is refused until step 1 has succeeded.</Text>}
        <Title order={4}>Steps</Title>
        {steps.map((s) => <StepCard key={s.id} step={s} />)}
      </Stack>
    </>
  );
}

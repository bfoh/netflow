import { Anchor, Card, Group, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { StateBadge } from '../components/Badges';
import { Hint } from '../components/Hint';
import { Notice } from '../components/Notice';
import { PageHeader, QueryState } from '../components/Page';
import { useSystemCrumbs } from '../features/systems/crumbs';
import { useDevice, useStaging } from '../hooks/queries';
import { StagingControls } from '../features/stage/StagingControls';
import { stagingStatus, stepTitle } from '../features/stage/staging';
import { fmtDate } from '../services/format';
import type { Deployment } from '../types/api';
import { stageLabel } from '../services/labels';
import { paths } from '../paths';

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
            {fmtDate(e.timestamp)} · {stageLabel(e.stage)} — {e.message}
          </Text>
        ))}
      </Stack>
      <Anchor component={Link} to={paths.plan(step.id)} size="sm" mt="xs">Open this step (all events, configuration after loading)</Anchor>
    </Card>
  );
}

export function StagingPage() {
  const { stagingId = '' } = useParams();
  const [started, setStarted] = useState(false);
  const plan = useStaging(stagingId, started);
  const steps = plan.data?.steps ?? [];
  const device = useDevice(steps[0]?.targets[0]?.device_id ?? '');
  const { running, done, ended } = stagingStatus(steps);
  const crumbs = useSystemCrumbs(steps[0]?.project_id, 'plans');

  return (
    <>
      <PageHeader title={`Staging plan${device.data ? ` · ${device.data.name}` : ''}`} breadcrumbs={crumbs}
        description={steps[0] ? `${steps.length} steps · made by ${steps[0].created_by} · ${fmtDate(steps[0].created_at)}${steps[0].approved_by ? ` · approved by ${steps[0].approved_by}` : ''}` : ''}
        actions={<StagingControls stagingId={stagingId} steps={steps} onStarted={() => setStarted(true)} />} />
      <QueryState isLoading={plan.isLoading} error={plan.error} />
      <Stack>
        {done && <Notice kind="success" title="Every step succeeded">
          Each step was checked on the device after it ran. Open a step for its events and the configuration read back.</Notice>}
        {ended && <Notice kind="error" title="The plan did not complete"
          details="To start again, make a new staging plan: a site file must land on a freshly restored base file.">
          A step did not succeed, so the steps after it did not run. Open that step for the reason.</Notice>}
        {running && <Notice kind="status" title="Running"
          details="Firmware and complete files restart the device (several minutes). Stop ends the running step at its next safe point, and the later steps do not run.">
          The steps run one after the other on the server, also if you leave this page.</Notice>}
        {!running && !done && !ended && <Hint>
          One approval covers every step. Steps after the first are checked when they run, because the earlier steps change the
          device; running a step on its own is refused until the steps before it have succeeded.</Hint>}
        <Title order={2} size="h4">Steps</Title>
        {steps.map((s) => <StepCard key={s.id} step={s} />)}
      </Stack>
    </>
  );
}

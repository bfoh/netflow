import { Accordion, Alert, Anchor, Button, Card, Group, Modal, Stack, Stepper, Text, Timeline, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconAlertTriangle, IconCheck, IconFlask, IconX } from '@tabler/icons-react';
import { Link, useParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { DiffView } from '../components/DiffView';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { useAction, useDeployment, useProjectDevices } from '../hooks/queries';
import { api } from '../services/api';
import type { Deployment } from '../types/api';

const STEPS = ['Validate & preview', 'Approve', 'Preflight', 'Back up', 'Deploy', 'Verify', 'Complete'];
const STEP_OF: Record<string, number> = {
  draft: 0, validating: 0, awaiting_approval: 1, ready: 2, preflight: 2, backing_up: 3,
  deploying: 4, verifying: 5, recovering: 5, succeeded: 7, rolled_back: 7, recovery_required: 7,
  failed: 7, cancelled: 7,
};
const OUTCOME: Record<string, { color: string; title: string; text: string }> = {
  succeeded: { color: 'teal', title: 'Deployment succeeded', text: 'Every changed device was verified against its intended configuration.' },
  failed: { color: 'red', title: 'Deployment failed before any change', text: 'No device was changed. See events for the reason.' },
  rolled_back: { color: 'orange', title: 'Deployment failed and was rolled back', text: 'Every changed device was automatically restored from its backup.' },
  recovery_required: { color: 'red', title: 'Manual recovery required', text: 'At least one device may be in an intermediate state. Check each target below before making further changes.' },
  cancelled: { color: 'gray', title: 'Deployment cancelled', text: 'No device was changed.' },
};
const TRANSIENT = new Set(['validating', 'preflight', 'backing_up', 'deploying', 'verifying', 'recovering']);

function Actions({ dep }: { dep: Deployment }) {
  const [confirm, { open, close }] = useDisclosure();
  const approve = useAction(() => api.approveDeployment(dep.id), 'Deployment approved');
  const execute = useAction(() => api.executeDeployment(dep.id), (d) => `Execution finished: ${d.state.replaceAll('_', ' ')}`);
  const cancel = useAction(() => api.cancelDeployment(dep.id), 'Deployment cancelled');
  const canCancel = ['draft', 'awaiting_approval', 'ready'].includes(dep.state);
  return (
    <Group>
      {dep.state === 'awaiting_approval' && <Button onClick={() => approve.mutate()} loading={approve.isPending}>Approve</Button>}
      {dep.state === 'ready' && <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={open}>{dep.dry_run ? 'Run dry run' : 'Execute deployment'}</Button>}
      {canCancel && <Button variant="default" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel</Button>}
      <Modal opened={confirm} onClose={close} title={dep.dry_run ? 'Run dry run' : 'Execute deployment'}>
        <Stack>
          <Text size="sm">
            {dep.dry_run
              ? `Connects to ${dep.targets.length} device(s), checks identity and compares configurations. Nothing is changed.`
              : `Backs up and then changes ${dep.targets.length} device(s) in ${dep.apply_mode} mode, verifies the result and rolls back where supported if anything fails.`}
          </Text>
          <Alert color="violet" icon={<IconFlask size={16} />} p="xs">All targets in this build are simulated devices; no physical equipment is contacted.</Alert>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Back</Button>
            <Button color={dep.dry_run ? 'indigo' : 'orange'} loading={execute.isPending} onClick={() => execute.mutate(undefined, { onSettled: close })}>Confirm</Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
  );
}

export function DeploymentDetailPage() {
  const { deploymentId = '' } = useParams();
  const dep = useDeployment(deploymentId);
  const devices = useProjectDevices(dep.data?.project_id ?? '');
  if (!dep.data) return <QueryState isLoading={dep.isLoading} error={dep.error} />;
  const d = dep.data;
  const byId = new Map((devices.data ?? []).map((x) => [x.id, x]));
  const outcome = OUTCOME[d.state];

  return (
    <>
      <PageHeader title={`${d.dry_run ? 'Dry run' : 'Deployment'} · ${fmtDate(d.created_at)}`}
        description={`Created by ${d.created_by}${d.approved_by ? ` · approved by ${d.approved_by} at ${fmtDate(d.approved_at)}` : ''} · ${d.apply_mode} mode`}
        actions={<><StateBadge state={d.state} /><Actions dep={d} /></>} />
      {TRANSIENT.has(d.state) && <Alert color="blue" mb="md">In progress: {d.state.replaceAll('_', ' ')}…</Alert>}
      {outcome && <Alert color={outcome.color} title={outcome.title} mb="md" icon={d.state === 'succeeded' ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />}>{outcome.text}</Alert>}
      <Card withBorder mb="md">
        <Stepper active={STEP_OF[d.state] ?? 0} size="xs" allowNextStepsSelect={false}
          color={['failed', 'recovery_required', 'rolled_back'].includes(d.state) ? 'red' : undefined}>
          {STEPS.map((s) => <Stepper.Step key={s} label={s} />)}
        </Stepper>
      </Card>

      <Title order={4} mb="xs">Targets</Title>
      <Accordion variant="separated" multiple mb="lg">
        {d.targets.map((t) => {
          const dev = byId.get(t.device_id);
          return (
            <Accordion.Item key={t.device_id} value={t.device_id}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" pr="sm">
                  <Group gap="xs">
                    <Text fw={600}>{dev?.name ?? t.device_id}</Text>
                    {dev && <EnvironmentBadge env={dev.environment} />}
                  </Group>
                  <StateBadge state={t.state} />
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  {t.message && <Text size="sm" c={t.state.includes('fail') || t.state.includes('manual') ? 'red' : undefined}>{t.message}</Text>}
                  <Text size="sm">
                    <Anchor component={Link} to={`/devices/${t.device_id}`}>Device</Anchor>
                    {' · '}configuration version <code>{t.config_version_id.slice(0, 8)}</code>
                    {t.backup_version_id && <> · backup <code>{t.backup_version_id.slice(0, 8)}</code></>}
                  </Text>
                  <Text size="sm" fw={600}>Proposed change</Text>
                  <DiffView diff={t.diff} />
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>

      <Title order={4} mb="xs">Events</Title>
      <Card withBorder>
        <Timeline bulletSize={18} lineWidth={2} active={d.events.length - 1}>
          {d.events.map((e) => (
            <Timeline.Item key={e.seq} color={e.status === 'error' ? 'red' : e.stage === 'lifecycle' ? 'indigo' : 'teal'}
              bullet={e.status === 'error' ? <IconX size={11} /> : undefined}
              title={<Text size="sm" fw={600}>{e.stage}{e.device_id ? ` · ${byId.get(e.device_id)?.name ?? ''}` : ''} — {e.status.replaceAll('_', ' ')}</Text>}>
              <Text size="sm" c="dimmed">{e.message}</Text>
              <Text size="xs" c="dimmed">{fmtDate(e.timestamp)}</Text>
            </Timeline.Item>
          ))}
        </Timeline>
      </Card>
    </>
  );
}

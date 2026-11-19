import { Accordion, Alert, Anchor, Badge, Button, Card, Group, Modal, Stack, Stepper, Text, TextInput, Timeline, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useEffect, useState } from 'react';
import { IconAlertTriangle, IconCheck, IconFlask, IconX } from '@tabler/icons-react';
import { Link, useParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { DiffView } from '../components/DiffView';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { RUNNING_STATES, useAction, useDeployment, useProjectDevices } from '../hooks/queries';
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

/** datetime-local value (local time) for a Date. */
const toLocalInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

function Actions({ dep, onRunning }: { dep: Deployment; onRunning: (running: boolean) => void }) {
  const [confirm, { open, close }] = useDisclosure();
  const [windowOpen, { open: openWindow, close: closeWindow }] = useDisclosure();
  const [start, setStart] = useState(() => toLocalInput(new Date()));
  const [end, setEnd] = useState(() => toLocalInput(new Date(Date.now() + 2 * 3600 * 1000)));
  const firmware = dep.kind === 'firmware';
  const approve = useAction(() => api.approveDeployment(dep.id, firmware
    ? { window_start: new Date(start).toISOString(), window_end: new Date(end).toISOString() } : undefined), 'Deployment approved');
  const execute = useAction(() => api.executeDeployment(dep.id), (d) => `Execution finished: ${d.state.replaceAll('_', ' ')}`);
  const cancel = useAction(() => api.cancelDeployment(dep.id), 'Deployment cancelled');
  const running = execute.isPending;
  useEffect(() => onRunning(running), [running, onRunning]);
  const canCancel = ['draft', 'awaiting_approval', 'ready'].includes(dep.state);
  return (
    <Group>
      {dep.state === 'awaiting_approval' && <Button onClick={() => (firmware ? openWindow() : approve.mutate())} loading={approve.isPending}>Approve</Button>}
      <Modal opened={windowOpen} onClose={closeWindow} title="Approve firmware upgrade">
        <Stack>
          <Text size="sm">Firmware upgrades can only run inside an approved maintenance window (maximum 24 hours). The approver must be
            a different person from the plan's creator.</Text>
          <TextInput type="datetime-local" label="Window start (your local time)" value={start} onChange={(e) => setStart(e.currentTarget.value)} />
          <TextInput type="datetime-local" label="Window end (your local time)" value={end} onChange={(e) => setEnd(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={closeWindow}>Back</Button>
            <Button loading={approve.isPending} onClick={() => approve.mutate(undefined, { onSuccess: closeWindow })}>Approve with this window</Button>
          </Group>
        </Stack>
      </Modal>
      {(dep.state === 'ready' || running) && <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={open} loading={running}>{dep.dry_run ? 'Run dry run' : 'Execute deployment'}</Button>}
      {canCancel && !running && <Button variant="default" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel</Button>}
      <Modal opened={confirm} onClose={close} title={dep.dry_run ? 'Run dry run' : 'Execute deployment'}>
        <Stack>
          <Text size="sm">
            {firmware
              ? (dep.dry_run
                ? `Connects to ${dep.targets.length} device(s) and reads identity and running version. Nothing is changed.`
                : `Upgrades ${dep.targets.length} device(s) one at a time: back up configuration, stage, install, reboot, wait for the device, verify the version. Stops at the first failure.`)
              : dep.dry_run
                ? `Connects to ${dep.targets.length} device(s), checks identity and compares configurations. Nothing is changed.`
                : `Backs up and then changes ${dep.targets.length} device(s) in ${dep.apply_mode} mode, verifies the result and rolls back where supported if anything fails.`}
          </Text>
          <Alert color="violet" icon={<IconFlask size={16} />} p="xs">Check the environment badge of every target below: simulated devices exist only in UNDM; lab devices are real equipment.</Alert>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Back</Button>
            <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={() => { close(); execute.mutate(); }}>Confirm</Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
  );
}

export function DeploymentDetailPage() {
  const { deploymentId = '' } = useParams();
  const [running, setRunning] = useState(false);
  const dep = useDeployment(deploymentId, running);
  const devices = useProjectDevices(dep.data?.project_id ?? '');
  if (!dep.data) return <QueryState isLoading={dep.isLoading} error={dep.error} />;
  const d = dep.data;
  const byId = new Map((devices.data ?? []).map((x) => [x.id, x]));
  const firmwareText: Record<string, string> = {
    succeeded: 'Every upgraded device came back and reports the target firmware version.',
    rolled_back: 'The upgrade did not complete. Every device that was touched runs its previous version; read each target\'s message below before trying again.',
  };
  const outcome = d.kind === 'firmware' && firmwareText[d.state]
    ? { ...OUTCOME[d.state], title: d.state === 'rolled_back' ? 'Upgrade did not complete' : OUTCOME[d.state].title, text: firmwareText[d.state] }
    : OUTCOME[d.state];
  const working = running || RUNNING_STATES.has(d.state);

  return (
    <>
      <PageHeader title={`${d.kind === 'firmware' ? 'Firmware upgrade' : 'Configuration deployment'}${d.dry_run ? ' (dry run)' : ''} · ${fmtDate(d.created_at)}`}
        description={`Created by ${d.created_by}${d.approved_by ? ` · approved by ${d.approved_by} at ${fmtDate(d.approved_at)}` : ''}${d.kind === 'firmware'
          ? (d.window_start ? ` · window ${fmtDate(d.window_start)} – ${fmtDate(d.window_end)}` : '') : ` · ${d.apply_mode} mode`}`}
        actions={<>{d.allow_downgrade && <Badge color="orange" variant="light">Downgrade to the approved version allowed</Badge>}<StateBadge state={d.state} /><Actions dep={d} onRunning={setRunning} /></>} />
      {working && (
        <Alert color="blue" mb="md" title={`In progress: ${RUNNING_STATES.has(d.state) ? d.state.replaceAll('_', ' ') : 'starting'}…`}>
          Keep this page open; the events below update as each step finishes.
          {d.kind === 'firmware' && !d.dry_run && ' A firmware upgrade takes several minutes per device: the image is transferred, written to flash, then the device restarts. Do not power off or unplug a device while this runs.'}
        </Alert>
      )}
      {!working && outcome && <Alert color={outcome.color} title={outcome.title} mb="md" icon={d.state === 'succeeded' ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />}>{outcome.text}</Alert>}
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
                    {t.to_version && <Badge variant="outline" color="gray">{t.from_version ?? '?'} → {t.to_version}</Badge>}
                  </Group>
                  <StateBadge state={t.state} />
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  {t.message && <Text size="sm" c={t.state.includes('fail') || t.state.includes('manual') ? 'red' : undefined}>{t.message}</Text>}
                  {t.credential_after_ref_id && (
                    <Text size="xs" c="dimmed">After loading, UNDM logs in with the credential chosen for this file and keeps it for the device.</Text>
                  )}
                  {t.secret_refs && Object.keys(t.secret_refs).length > 0 && (
                    <Text size="xs" c="dimmed">{Object.keys(t.secret_refs).length} secret setting(s) filled from the credential store when sent (values are never shown).</Text>
                  )}
                  <Text size="sm">
                    <Anchor component={Link} to={`/devices/${t.device_id}`}>Device</Anchor>
                    {t.config_version_id && <>{' · '}configuration version <code>{t.config_version_id.slice(0, 8)}</code></>}
                    {t.backup_version_id && <> · backup <code>{t.backup_version_id.slice(0, 8)}</code></>}
                  </Text>
                  {d.kind === 'configuration' && <><Text size="sm" fw={600}>Proposed change</Text><DiffView diff={t.diff} /></>}
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

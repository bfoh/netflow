import { Accordion, Alert, Anchor, Badge, Button, Card, Code, CopyButton, Group, Modal, Stack, Stepper, Text, TextInput, Timeline, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
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
// A dry run is not approved and goes from preflight straight to its end: no backup, change or verification.
const DRY_STEPS = ['Validate & preview', 'Preflight (read only)', 'Complete'];
const DRY_STEP_OF: Record<string, number> = {
  draft: 0, validating: 0, ready: 1, preflight: 1, succeeded: 3, failed: 3, cancelled: 3,
};
const OUTCOME: Record<string, { color: string; title: string; text: string }> = {
  succeeded: { color: 'teal', title: 'Deployment succeeded', text: 'Every changed device was verified against its intended configuration.' },
  failed: { color: 'red', title: 'Deployment failed before any change', text: 'No device was changed. See events for the reason.' },
  rolled_back: { color: 'orange', title: 'Deployment failed and was rolled back', text: 'Every changed device was automatically restored from its backup.' },
  recovery_required: { color: 'red', title: 'Manual recovery required', text: 'At least one device may be in an intermediate state. Check each target below before making further changes.' },
  cancelled: { color: 'gray', title: 'Deployment cancelled', text: 'No device was changed.' },
};

/** datetime-local value in UTC for a Date (UNDM shows and takes times in UTC, like the network). */
const toUtcInput = (d: Date) => d.toISOString().slice(0, 16);
/** A datetime-local value typed in UTC, as an ISO time. */
const fromUtcInput = (v: string) => new Date(`${v}:00Z`).toISOString();

function Actions({ dep, onRunning }: { dep: Deployment; onRunning: (running: boolean) => void }) {
  const [confirm, { open, close }] = useDisclosure();
  const [windowOpen, { open: openWindow, close: closeWindow }] = useDisclosure();
  const [start, setStart] = useState(() => toUtcInput(new Date()));
  const [end, setEnd] = useState(() => toUtcInput(new Date(Date.now() + 2 * 3600 * 1000)));
  const firmware = dep.kind === 'firmware';
  const approve = useAction(() => api.approveDeployment(dep.id, firmware
    ? { window_start: fromUtcInput(start), window_end: fromUtcInput(end) } : undefined), 'Deployment approved');
  const [started, setStarted] = useState(false);
  const [stopOpen, { open: openStop, close: closeStop }] = useDisclosure();
  const execute = useAction(() => api.executeDeployment(dep.id),
    'Run started on the server; the events below show each step');
  const stop = useAction(() => api.stopDeployment(dep.id), 'Stop requested');
  const cancel = useAction(() => api.cancelDeployment(dep.id), 'Deployment cancelled');
  // Between the start request and the first stored step the plan still reads "ready".
  const running = execute.isPending || (started && dep.state === 'ready');
  const active = running || RUNNING_STATES.has(dep.state);
  useEffect(() => onRunning(running), [running, onRunning]);
  const canCancel = ['draft', 'awaiting_approval', 'ready'].includes(dep.state);
  return (
    <Group>
      {dep.state === 'awaiting_approval' && <Button onClick={() => (firmware ? openWindow() : approve.mutate())} loading={approve.isPending}>Approve</Button>}
      <Modal opened={windowOpen} onClose={closeWindow} title="Approve firmware upgrade">
        <Stack>
          <Text size="sm">Firmware upgrades can only run inside an approved maintenance window (maximum 24 hours). The approver must be
            a different person from the plan's creator.</Text>
          <TextInput type="datetime-local" label="Window start (UTC)" value={start} onChange={(e) => setStart(e.currentTarget.value)} />
          <TextInput type="datetime-local" label="Window end (UTC)" value={end} onChange={(e) => setEnd(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={closeWindow}>Back</Button>
            <Button loading={approve.isPending} onClick={() => approve.mutate(undefined, { onSuccess: closeWindow })}>Approve with this window</Button>
          </Group>
        </Stack>
      </Modal>
      {dep.state === 'ready' && !started && <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={open} loading={running}>{dep.dry_run ? 'Run dry run' : 'Execute deployment'}</Button>}
      {canCancel && !active && <Button variant="default" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel</Button>}
      {active && <Button color="red" variant="light" onClick={openStop} loading={stop.isPending}
        disabled={stop.isSuccess}>{stop.isSuccess ? 'Stopping…' : 'Stop'}</Button>}
      <Modal opened={stopOpen} onClose={closeStop} title="Stop this deployment?">
        <Stack>
          <Text size="sm">UNDM stops at the next safe point: between steps, while waiting for a device to come back, or
            while waiting for a device's answer. A command a device is already carrying out (a transfer, a restart) is not
            undone, and no rollback is started.</Text>
          <Text size="sm">If a device may already have been changed, the plan ends as <b>manual recovery required</b> and names
            it: check that device before making further changes. If nothing was changed yet, it ends as <b>failed</b>.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeStop}>Back</Button>
            <Button color="red" onClick={() => { closeStop(); stop.mutate(); }}>Stop</Button>
          </Group>
        </Stack>
      </Modal>
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
            <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={() => { close(); setStarted(true); execute.mutate(undefined, { onError: () => setStarted(false) }); }}>Confirm</Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
  );
}

const RESTART_STEP = /^(waiting for the device to answer|loading the file: )/;
const fmtElapsed = (ms: number) => { const s = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const zoned = (ts: string) => (/([zZ]|[+-]\d\d:?\d\d)$/.test(ts) ? ts : `${ts}Z`);

/** What is happening now, for how long, and whether a device is restarting (be patient). */
function Progress({ d, names }: { d: Deployment; names: Map<string, { name: string }> }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  const last = d.events[d.events.length - 1];
  const since = last ? now - new Date(zoned(last.timestamp)).getTime() : 0;
  const device = last?.device_id ? names.get(last.device_id)?.name ?? 'The device' : 'The device';
  const restarting = !!last && RESTART_STEP.test(last.message);
  return (
    <Stack gap="xs" mb="md">
      {restarting && (
        <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title={`${device} is restarting: please wait (${fmtElapsed(since)})`}>
          A restart takes about 1–2 minutes (2930F on the bench: about 1 minute). UNDM checks every 20 seconds and continues by
          itself as soon as the device answers. <b>Do not power it off or unplug it.</b> If the device's management port changes
          with the new configuration, connect this PC there now (the event below says where).
        </Alert>
      )}
      <Alert color="blue" title={`In progress: ${RUNNING_STATES.has(d.state) ? d.state.replaceAll('_', ' ') : 'starting'}…`}>
        {last && <Text size="sm" mb={4}>Latest step ({fmtElapsed(since)} ago): {last.message}</Text>}
        The run continues on the server even if you leave this page; the events below update as each step finishes.
        Use <b>Stop</b> to end it at the next safe point.
        {d.kind === 'firmware' && !d.dry_run && ' A firmware upgrade takes several minutes per device: the image is transferred, written to flash, then the device restarts. Do not power off or unplug a device while this runs.'}
      </Alert>
    </Stack>
  );
}

/** The running configuration read back after the change: view it, or compare it with what was sent. */
function AfterConfig({ afterId, sentId }: { afterId: string; sentId: string | null }) {
  const [mode, setMode] = useState<'view' | 'compare' | null>(null);
  const after = useQuery({ queryKey: ['config', afterId], queryFn: () => api.config(afterId), enabled: mode !== null });
  const diff = useQuery({ queryKey: ['config-diff', sentId, afterId], queryFn: () => api.configDiff(sentId!, afterId),
    enabled: mode === 'compare' && !!sentId });
  return (
    <>
      <Group gap="xs">
        <Button size="xs" variant="light" onClick={() => setMode('view')}>View configuration after deployment</Button>
        {sentId && <Button size="xs" variant="default" onClick={() => setMode('compare')}>Compare with what was sent</Button>}
      </Group>
      <Modal opened={mode !== null} onClose={() => setMode(null)} size="xl"
        title={mode === 'compare' ? 'Sent (−) compared with the device after deployment (+)' : 'Configuration on the device after deployment'}>
        {mode === 'view' && (after.data
          ? <><Text size="xs" c="dimmed" mb="xs">Read back from the device by UNDM after the change ({after.data.reference}).</Text>
            <Code block style={{ maxHeight: '65vh', overflow: 'auto' }}>{after.data.text}</Code></>
          : <QueryState isLoading={after.isLoading} error={after.error} />)}
        {mode === 'compare' && (diff.data
          ? <><Text size="xs" c="dimmed" mb="xs">Lines only in what was sent are marked −; lines only on the device are marked +.
            A device often does not list settings that equal its defaults, and adds lines of its own.</Text>
            <div style={{ maxHeight: '65vh', overflow: 'auto' }}><DiffView diff={diff.data.unified} /></div></>
          : <QueryState isLoading={diff.isLoading} error={diff.error} />)}
      </Modal>
    </>
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
  const dryText: Record<string, { title: string; text: string }> = {
    succeeded: { title: 'Dry run succeeded', text: d.kind === 'firmware'
      ? 'Every device was reached, its identity checked and its running version read. Nothing was changed: run a real plan to upgrade.'
      : 'Every device was reached, its identity checked and its configuration compared. Nothing was changed.' },
    failed: { title: 'Dry run failed', text: 'No device was changed. See events for the reason.' },
    cancelled: { title: 'Dry run cancelled', text: 'No device was changed.' },
  };
  const outcome = d.dry_run && dryText[d.state] && OUTCOME[d.state]
    ? { ...OUTCOME[d.state], ...dryText[d.state] }
    : d.kind === 'firmware' && firmwareText[d.state]
      ? { ...OUTCOME[d.state], title: d.state === 'rolled_back' ? 'Upgrade did not complete' : OUTCOME[d.state].title, text: firmwareText[d.state] }
      : OUTCOME[d.state];
  const steps = d.dry_run ? DRY_STEPS : STEPS;
  const stepOf = d.dry_run ? DRY_STEP_OF : STEP_OF;
  const working = running || RUNNING_STATES.has(d.state);

  return (
    <>
      <PageHeader title={`${d.kind === 'firmware' ? 'Firmware upgrade' : 'Configuration deployment'}${d.dry_run ? ' (dry run)' : ''} · ${fmtDate(d.created_at)}`}
        description={`Created by ${d.created_by}${d.approved_by ? ` · approved by ${d.approved_by} at ${fmtDate(d.approved_at)}` : ''}${d.kind === 'firmware'
          ? (d.window_start ? ` · window ${fmtDate(d.window_start)} – ${fmtDate(d.window_end)}` : '') : ` · ${d.apply_mode} mode`}`}
        actions={<>{d.allow_downgrade && <Badge color="orange" variant="light">Downgrade to the approved version allowed</Badge>}{d.also_secondary && <Badge color="blue" variant="light">Secondary flash too</Badge>}<StateBadge state={d.state} /><Actions dep={d} onRunning={setRunning} /></>} />
      {d.staging_id && (
        <Alert color="grape" mb="md" p="xs" title={`Step ${d.staging_step} of a staging plan`}>
          {d.staging_step === 1 ? 'The base file. The site file (step 2) runs after this step has succeeded. '
            : 'The site file. It runs only after step 1 (the base file) has succeeded. '}
          <Anchor component={Link} to={`/staging/${d.staging_id}`}>Open the staging plan</Anchor>
        </Alert>
      )}
      {working && <Progress d={d} names={byId} />}
      {!working && outcome && <Alert color={outcome.color} title={outcome.title} mb="md" icon={d.state === 'succeeded' ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />}>{outcome.text}</Alert>}
      <Card withBorder mb="md">
        <Stepper active={stepOf[d.state] ?? 0} size="xs" allowNextStepsSelect={false}
          color={['failed', 'recovery_required', 'rolled_back'].includes(d.state) ? 'red' : undefined}>
          {steps.map((s) => <Stepper.Step key={s} label={s} />)}
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
                    {t.config_version_id && <>{' · '}<Anchor component={Link} to={`/configurations?device=${t.device_id}&version=${t.config_version_id}`}>configuration sent</Anchor> <code>{t.config_version_id.slice(0, 8)}</code></>}
                    {t.backup_version_id && <>{' · '}<Anchor component={Link} to={`/configurations?device=${t.device_id}&version=${t.backup_version_id}`}>backup before</Anchor> <code>{t.backup_version_id.slice(0, 8)}</code></>}
                    {t.after_version_id && <>{' · '}<Anchor component={Link} to={`/configurations?device=${t.device_id}&version=${t.after_version_id}`}>after deployment</Anchor> <code>{t.after_version_id.slice(0, 8)}</code></>}
                  </Text>
                  {t.after_version_id && <AfterConfig afterId={t.after_version_id} sentId={t.config_version_id} />}
                  {d.kind === 'configuration' && <><Text size="sm" fw={600}>Proposed change</Text><DiffView diff={t.diff} /></>}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>

      <Group justify="space-between" mb="xs">
        <Title order={4}>Events ({d.events.length})</Title>
        <CopyButton value={d.events.map((e) => `${fmtDate(e.timestamp)}  ${e.stage}${e.device_id ? ` · ${byId.get(e.device_id)?.name ?? ''}` : ''} — ${e.status}: ${e.message}`).join('\n')}>
          {({ copied, copy }) => <Button size="xs" variant="light" onClick={copy}>{copied ? 'Copied' : 'Copy events as text'}</Button>}
        </CopyButton>
      </Group>
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

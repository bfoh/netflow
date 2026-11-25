import { Accordion, Anchor, Badge, Button, Card, Code, CopyButton, Group, Modal, Stack, Stepper, Text, Textarea, TextInput, Timeline, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { IconAlertTriangle, IconTrash, IconX } from '@tabler/icons-react';
import { Link, useNavigate, useParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { DiffView } from '../components/DiffView';
import { PageHeader, QueryState } from '../components/Page';
import { Hint } from '../components/Hint';
import { Notice, type NoticeKind } from '../components/Notice';
import { SafetyHint } from '../components/SafetyHint';
import { fmtDate } from '../services/format';
import { RUNNING_STATES, useAction, useDeployment, usePolicy, useProjectDevices } from '../hooks/queries';
import { api } from '../services/api';
import type { Deployment } from '../types/api';
import { applyModeLabel, stageLabel, stateLabel } from '../services/labels';
import { DialogError } from '../components/ConfirmDialog';
import { useConfirm } from '../hooks/useConfirm';
import { usePlanDelete } from '../hooks/usePlanDelete';

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
const OUTCOME: Record<string, { kind: NoticeKind; title: string; text: string }> = {
  succeeded: { kind: 'success', title: 'Plan succeeded', text: 'Every changed device was verified against its intended configuration.' },
  failed: { kind: 'error', title: 'Plan failed before any change', text: 'No device was changed. The events below say why.' },
  rolled_back: { kind: 'caution', title: 'Plan failed and the device was put back', text: 'Every changed device was automatically restored from its backup.' },
  recovery_required: { kind: 'error', title: 'Needs attention', text: 'A device may be half-changed. Check each device below (for example on its console) before making further changes.' },
  cancelled: { kind: 'settled', title: 'Plan cancelled', text: 'No device was changed.' },
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
    ? { window_start: fromUtcInput(start), window_end: fromUtcInput(end) } : undefined), 'Plan approved',
    { errorInDialog: firmware });
  const policy = usePolicy();
  const [ask, confirmDialog] = useConfirm();
  const [started, setStarted] = useState(false);
  const [stopOpen, { open: openStop, close: closeStop }] = useDisclosure();
  const execute = useAction(() => api.executeDeployment(dep.id),
    'Run started on the server; the events below show each step');
  const stop = useAction(() => api.stopDeployment(dep.id), 'Stop requested');
  const cancel = useAction(() => api.cancelDeployment(dep.id), 'Plan cancelled', { errorInDialog: true });
  // Between the start request and the first stored step the plan still reads "ready".
  const running = execute.isPending || (started && dep.state === 'ready');
  const active = running || RUNNING_STATES.has(dep.state);
  useEffect(() => onRunning(running), [running, onRunning]);
  const canCancel = ['draft', 'awaiting_approval', 'ready'].includes(dep.state);
  const [askToDelete, deleteDialog, canDelete] = usePlanDelete();
  const navigate = useNavigate();
  const devices = useProjectDevices(dep.project_id);
  const realNames = dep.targets.map((t) => devices.data?.find((x) => x.id === t.device_id))
    .filter((x) => x && x.environment !== 'simulated').map((x) => x!.name);
  const decide = !dep.dry_run && ['awaiting_approval', 'ready'].includes(dep.state) && !active;
  return (
    <Stack gap={4} align="flex-end">
    <Group>
      {dep.state === 'awaiting_approval' && <Button onClick={() => (firmware ? openWindow() : approve.mutate())} loading={approve.isPending}>Approve</Button>}
      <Modal opened={windowOpen} onClose={closeWindow} title="Approve firmware upgrade">
        <Stack>
          <Text size="sm">Firmware upgrades can only run inside an approved maintenance window (maximum 24 hours).
            {policy.data?.firmware_require_separate_approver !== false
              ? ` The approver must be a different person from the plan's maker (${dep.created_by}).` : ''}</Text>
          <TextInput type="datetime-local" label="Window start (UTC)" value={start} onChange={(e) => setStart(e.currentTarget.value)} />
          <TextInput type="datetime-local" label="Window end (UTC)" value={end} onChange={(e) => setEnd(e.currentTarget.value)} />
          <DialogError error={approve.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={closeWindow}>Back</Button>
            <Button loading={approve.isPending} onClick={() => approve.mutate(undefined, { onSuccess: closeWindow })}>Approve with this window</Button>
          </Group>
        </Stack>
      </Modal>
      {dep.state === 'ready' && !started && <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={open} loading={running}>{dep.dry_run ? 'Run dry run' : 'Run plan'}</Button>}
      {canCancel && !active && <Button variant="default" loading={cancel.isPending} onClick={() => ask({
        title: 'Cancel this plan?', confirmLabel: 'Cancel plan',
        message: 'The plan will not run and cannot be approved or run later. No device has been changed by it. Make a new plan if you need it again.',
        onConfirm: () => cancel.mutateAsync(),
      })}>Cancel plan</Button>}
      {confirmDialog}
      {deleteDialog}
      {!active && canDelete(dep) && <Button variant="subtle" color="red" leftSection={<IconTrash size={16} />}
        onClick={() => askToDelete(dep, () => void navigate('/deployments'))}>Delete</Button>}
      {active && <Button color="red" variant="light" onClick={openStop} loading={stop.isPending}
        disabled={stop.isSuccess}>{stop.isSuccess ? 'Stopping…' : 'Stop'}</Button>}
      <Modal opened={stopOpen} onClose={closeStop} title="Stop this plan?">
        <Stack>
          <Text size="sm">UNDM stops at the next safe point: between steps, while waiting for a device to come back, or
            while waiting for a device's answer. A command a device is already carrying out (a transfer, a restart) is not
            undone, and no rollback is started.</Text>
          <Text size="sm">If a device may already have been changed, the plan ends as <b>Needs attention</b> and names
            it: check that device before making further changes. If nothing was changed yet, it ends as <b>Failed</b>.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeStop}>Back</Button>
            <Button color="red" onClick={() => { closeStop(); stop.mutate(); }}>Stop</Button>
          </Group>
        </Stack>
      </Modal>
      <Modal opened={confirm} onClose={close} title={dep.dry_run ? 'Run dry run' : 'Run plan'}>
        <Stack>
          <Text size="sm">
            {firmware
              ? (dep.dry_run
                ? `Connects to ${dep.targets.length} device(s) and reads identity and running version. Nothing is changed.`
                : `Upgrades ${dep.targets.length} device(s) one at a time: back up configuration, stage, install, reboot, wait for the device, verify the version. Stops at the first failure.`)
              : dep.dry_run
                ? `Connects to ${dep.targets.length} device(s), checks identity and compares configurations. Nothing is changed.`
                : `Backs up and then changes ${dep.targets.length} device(s) with ${applyModeLabel(dep.apply_mode)}, verifies the result and puts the device back where it can if anything fails.`}
          </Text>
          {realNames.length > 0 && !dep.dry_run
            ? <Notice kind="caution" compact title={`${realNames.length === 1 ? 'A real device' : `${realNames.length} real devices`} will be changed`}>
                {realNames.join(', ')}: equipment on your bench, not a simulation.</Notice>
            : <Hint>{dep.dry_run ? 'A dry run only reads from the devices.' : 'Every device in this plan is simulated: nothing real is touched.'}</Hint>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Back</Button>
            <Button color={dep.dry_run ? 'indigo' : 'orange'} onClick={() => { close(); setStarted(true); execute.mutate(undefined, { onError: () => setStarted(false) }); }}>Confirm</Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
    {decide && <SafetyHint real={realNames.length > 0} firmware={firmware} />}
    </Stack>
  );
}

const SHOWN_EVENTS = 40;

/** A plan's events; long runs show the latest ones first, with the rest one click away. */
function EventList({ events, names }: { events: Deployment['events']; names: Map<string, { name: string }> }) {
  const [all, setAll] = useState(false);
  const hidden = all ? 0 : Math.max(0, events.length - SHOWN_EVENTS);
  const shown = events.slice(hidden);
  return (
    <Card withBorder>
      {hidden > 0 && <Button size="xs" variant="subtle" mb="sm" onClick={() => setAll(true)}>Show the {hidden} earlier events</Button>}
      <Timeline bulletSize={18} lineWidth={2} active={shown.length - 1}>
        {shown.map((e) => (
          <Timeline.Item key={e.seq} color={e.status === 'error' ? 'red' : e.status === 'warning' ? 'orange' : e.stage === 'lifecycle' ? 'indigo' : 'teal'}
            bullet={e.status === 'error' ? <IconX size={11} /> : e.status === 'warning' ? <IconAlertTriangle size={11} /> : undefined}
            title={<Text size="sm" fw={600}>{stageLabel(e.stage)}{e.device_id ? ` · ${names.get(e.device_id)?.name ?? ''}` : ''} — {stateLabel(e.status)}</Text>}>
            <Text size="sm" c="dimmed" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{e.message}</Text>
            <Text size="xs" c="dimmed">{fmtDate(e.timestamp)}</Text>
          </Timeline.Item>
        ))}
      </Timeline>
    </Card>
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
        <Notice kind="caution" title={`${device} is restarting: please wait (${fmtElapsed(since)})`}
          details={<>A restart takes about 1–2 minutes (2930F on the bench: about 1 minute). UNDM checks every 20 seconds and
            continues by itself as soon as the device answers. If the device's management port changes with the new
            configuration, connect this PC there now (the latest event says where).</>}>
          Do not power it off or unplug it. UNDM continues by itself when it answers.
        </Notice>
      )}
      <Notice kind="status" title={`Running: ${RUNNING_STATES.has(d.state) ? stateLabel(d.state).toLowerCase() : 'starting'}…`}
        details={<>The run continues on the server even if you leave this page. Use <b>Stop</b> to end it at the next safe
          point.{d.kind === 'firmware' && !d.dry_run && ' A firmware upgrade takes several minutes per device: the image is transferred, written to flash, then the device restarts.'}</>}>
        {last ? <>Latest step ({fmtElapsed(since)} ago): {last.message}</> : 'Starting…'}
      </Notice>
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
        <Button size="xs" variant="light" onClick={() => setMode('view')}>View configuration after the plan</Button>
        {sentId && <Button size="xs" variant="default" onClick={() => setMode('compare')}>Compare with what was sent</Button>}
      </Group>
      <Modal opened={mode !== null} onClose={() => setMode(null)} size="xl"
        title={mode === 'compare' ? 'Sent (−) compared with the device afterwards (+)' : 'Configuration on the device afterwards'}>
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

/** A plan that needs attention: who checked it, or the later plan that did; else "Mark as checked…" (D-088). */
function AttentionPanel({ d }: { d: Deployment }) {
  const [opened, { open, close }] = useDisclosure();
  const [note, setNote] = useState('');
  const mark = useAction(() => api.markChecked(d.id, note), 'Marked as checked', { errorInDialog: true });
  const cleared = d.attention_cleared;
  if (cleared === 'checked') {
    const ev = [...d.events].reverse().find((e) => e.status === 'checked');
    return <Notice kind="settled" mb="md" title="Needs attention · checked">{ev?.message ?? 'A person checked the device.'}</Notice>;
  }
  if (cleared?.startsWith('superseded:')) {
    return (
      <Notice kind="settled" mb="md" title="Needs attention · a later plan succeeded">
        <Anchor component={Link} to={`/deployments/${cleared.slice('superseded:'.length)}`} size="sm">That plan</Anchor> changed
        and verified the same device(s) afterwards, so this one no longer waits for a check.
      </Notice>
    );
  }
  return (
    <>
      <Notice kind="error" mb="md" title={OUTCOME.recovery_required.title}
        action={<Button size="xs" variant="white" color="red" onClick={() => { setNote(''); mark.reset(); open(); }}>Mark as checked…</Button>}>
        {OUTCOME.recovery_required.text} When it is as it should be, mark the plan as checked: it then no longer waits on Home.
      </Notice>
      <Modal opened={opened} onClose={close} title="Mark as checked">
        <Stack>
          <Textarea label="What did you check?" description="Kept in the plan's events and the audit log."
            placeholder="e.g. console: show running-config matches the file; device saved" autosize minRows={2}
            maxLength={500} value={note} onChange={(e) => setNote(e.currentTarget.value)} data-autofocus />
          <DialogError error={mark.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Back</Button>
            <Button disabled={note.trim().length < 5} loading={mark.isPending}
              onClick={() => mark.mutate(undefined, { onSuccess: close })}>Mark as checked</Button>
          </Group>
        </Stack>
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
    : d.kind === 'first_login' && d.state === 'succeeded'
      ? { ...OUTCOME[d.state], text: 'The unit now has the device\'s login, and UNDM logged in with it. Next: the firmware plan, then the staging plan (base and site files).' }
    : d.kind === 'firmware' && firmwareText[d.state]
      ? { ...OUTCOME[d.state], title: d.state === 'rolled_back' ? 'Upgrade did not complete' : OUTCOME[d.state].title, text: firmwareText[d.state] }
      : OUTCOME[d.state];
  const steps = d.dry_run ? DRY_STEPS : STEPS;
  const stepOf = d.dry_run ? DRY_STEP_OF : STEP_OF;
  const working = running || RUNNING_STATES.has(d.state);

  return (
    <>
      <PageHeader title={`${d.kind === 'firmware' ? 'Firmware upgrade' : d.kind === 'first_login' ? 'First login (new unit)' : d.kind === 'free_address' ? 'Temporary address (make room)' : 'Configuration plan'}${d.dry_run ? ' (dry run)' : ''} · ${fmtDate(d.created_at)}`}
        description={`Created by ${d.created_by}${d.approved_by ? ` · approved by ${d.approved_by} at ${fmtDate(d.approved_at)}` : ''}${d.kind === 'firmware'
          ? (d.window_start ? ` · window ${fmtDate(d.window_start)} – ${fmtDate(d.window_end)}` : '') : d.kind === 'first_login' ? '' : ` · ${d.apply_mode} mode`}`}
        actions={<>{d.allow_downgrade && <Badge color="orange" variant="light">Downgrade to the approved version allowed</Badge>}{d.also_secondary && <Badge color="blue" variant="light">Secondary flash too</Badge>}<StateBadge state={d.state} /><Actions dep={d} onRunning={setRunning} /></>} />
      {d.staging_id && (
        <Hint mb="md">Step {d.staging_step} of a <Anchor component={Link} to={`/staging/${d.staging_id}`} size="xs">staging plan</Anchor>
          {d.staging_step === 1 ? ': the next step runs only after this one has succeeded.'
            : `: it runs only after steps 1–${(d.staging_step ?? 2) - 1} have succeeded.`}</Hint>
      )}
      {working && <Progress d={d} names={byId} />}
      {!working && outcome && d.state !== 'recovery_required' && <Notice kind={outcome.kind} title={outcome.title} mb="md">{outcome.text}</Notice>}
      {!working && d.state === 'recovery_required' && <AttentionPanel d={d} />}
      <Card withBorder mb="md">
        <Stepper active={stepOf[d.state] ?? 0} size="xs" allowNextStepsSelect={false}
          color={['failed', 'recovery_required', 'rolled_back'].includes(d.state) ? 'red' : undefined}>
          {steps.map((s) => <Stepper.Step key={s} label={s} />)}
        </Stepper>
      </Card>

      <Title order={2} size="h4" mb="xs">Targets</Title>
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
                    {t.after_version_id && <>{' · '}<Anchor component={Link} to={`/configurations?device=${t.device_id}&version=${t.after_version_id}`}>afterwards</Anchor> <code>{t.after_version_id.slice(0, 8)}</code></>}
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
        <Title order={2} size="h4">Events ({d.events.length})</Title>
        <CopyButton value={d.events.map((e) => `${fmtDate(e.timestamp)}  ${e.stage}${e.device_id ? ` · ${byId.get(e.device_id)?.name ?? ''}` : ''} — ${e.status}: ${e.message}`).join('\n')}>
          {({ copied, copy }) => <Button size="xs" variant="light" onClick={copy}>{copied ? 'Copied' : 'Copy events as text'}</Button>}
        </CopyButton>
      </Group>
      <EventList events={d.events} names={byId} />
    </>
  );
}

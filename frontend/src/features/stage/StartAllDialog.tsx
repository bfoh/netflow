import { Button, Group, List, Modal, Stack, Text } from '@mantine/core';
import { IconCheck, IconClock } from '@tabler/icons-react';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { InlineStatus } from '../../components/InlineStatus';
import { Notice } from '../../components/Notice';
import { ReasonButton } from '../../components/ReasonButton';
import { SafetyHint } from '../../components/SafetyHint';
import { useAction, usePolicy } from '../../hooks/queries';
import { api, getActor } from '../../services/api';
import { ApproveFields } from '../plans/ApproveFields';
import { approveAlone, needsSecondPerson, soloOffered } from '../plans/soloApproval';
import { defaultWindow, windowBody, windowProblem } from '../plans/window';
import { failureReason } from './staging';
import type { StartItem } from './startOrder';

type Outcome = { name: string; ok: boolean; text: string };

/**
 * Start all ready (D-121): every device that can start now gets its plan made (or uses the one
 * waiting), approved and run, in the order of the roles, after one confirmation. The others
 * wait, and the dialog says why. Each plan goes through the lifecycle exactly as on its card.
 */
export function StartAllDialog({ opened, onClose, projectId, items }: {
  opened: boolean; onClose: () => void; projectId: string; items: StartItem[];
}) {
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title="Start all ready devices">
      {opened && <StartAllBody projectId={projectId} items={items} onClose={onClose} />}
    </Modal>
  );
}

function StartAllBody({ projectId, items, onClose }: { projectId: string; items: StartItem[]; onClose: () => void }) {
  const policy = usePolicy();
  const actor = getActor();
  const ready = items.filter((i) => i.ready);
  const waiting = items.filter((i) => !i.ready);
  const firmware = ready.some((i) => i.firmware);
  const real = ready.filter((i) => i.device.environment !== 'simulated');
  const fwReal = real.some((i) => i.firmware || i.steps.some((s) => s.kind === 'firmware'));
  const [win, setWin] = useState(defaultWindow);
  const [solo, setSolo] = useState(false);
  const [outcomes, setOutcomes] = useState<Outcome[] | null>(null);
  // New plans are made by this person; a second person is needed for their firmware steps.
  const second = needsSecondPerson(policy.data, { firmware, maker: actor, actor });
  const offered = soloOffered(policy.data, { firmware, maker: actor, actor });
  const p = policy.data;
  const allowed = real.length === 0 || (!!p?.enable_real_device_writes && (!fwReal || !!p?.enable_real_device_firmware));
  const blocked = ready.length === 0 ? 'No device is ready to start.'
    : firmware && windowProblem(win) ? 'Correct the window first.'
      : second && !(offered && solo) ? (offered ? 'Tick “I am staging alone”, or let a second person approve.' : 'A second person must approve the firmware steps.')
        : !allowed ? 'Turn the safety switch on first (above).' : null;

  const start = useAction(async () => {
    const results: Outcome[] = [];
    const toApprove: { name: string; stagingId: string; firmware: boolean }[] = [];
    const toRun: { name: string; stagingId: string }[] = [];
    // 1. Make (or take) each plan; a plan whose check found a problem is not started.
    for (const item of ready) {
      const plan = item.stagingId ? await api.staging(item.stagingId)
        : await api.createDeviceStaging(projectId, { device_id: item.device.id, steps: item.steps });
      const bad = plan.steps.find((s) => !['awaiting_approval', 'ready', 'succeeded'].includes(s.state));
      if (bad) {
        results.push({ name: item.device.name, ok: false, text: `its check found a problem: ${failureReason(plan.steps)?.text ?? bad.state}` });
        continue;
      }
      if (plan.steps.some((s) => s.state === 'awaiting_approval')) {
        toApprove.push({ name: item.device.name, stagingId: plan.staging_id,
          firmware: plan.steps.some((s) => s.kind === 'firmware' && s.state === 'awaiting_approval') });
      }
      toRun.push({ name: item.device.name, stagingId: plan.staging_id });
    }
    // 2. Approve them all (staging alone: the rule is off once for all, and on again at once).
    const failedApproval = new Set<string>();
    const approveAll = async () => {
      for (const a of toApprove) {
        try {
          await api.approveStaging(a.stagingId, a.firmware ? windowBody(win) : undefined);
        } catch (e) {
          failedApproval.add(a.stagingId);
          results.push({ name: a.name, ok: false, text: `not approved: ${e instanceof Error ? e.message : String(e)}` });
        }
      }
    };
    await (second && solo && toApprove.some((a) => a.firmware) ? approveAlone(approveAll) : approveAll());
    // 3. Run them, one request each: the runs go on side by side on the server.
    for (const r of toRun.filter((x) => !failedApproval.has(x.stagingId))) {
      try {
        await api.executeStaging(r.stagingId);
        results.push({ name: r.name, ok: true, text: 'started' });
      } catch (e) {
        results.push({ name: r.name, ok: false, text: `not started: ${e instanceof Error ? e.message : String(e)}` });
      }
    }
    setOutcomes(results);
  }, undefined, { errorInDialog: true });

  if (outcomes) {
    return (
      <Stack>
        <List spacing={4} size="sm" listStyleType="none">
          {outcomes.map((o) => (
            <List.Item key={o.name}>
              <InlineStatus tone={o.ok ? 'success' : 'danger'} size="sm">{o.name}: {o.text}</InlineStatus>
            </List.Item>
          ))}
        </List>
        <Group justify="flex-end"><Button onClick={onClose} data-autofocus>Close</Button></Group>
      </Stack>
    );
  }
  return (
    <Stack>
      <div>
        <Text size="sm" fw={600} mb={4}>Starts now ({ready.length})</Text>
        {ready.length === 0 ? <Text size="sm" c="dimmed">None.</Text> : (
          <List size="sm" spacing={2} icon={<IconCheck size={14} aria-hidden />}>
            {ready.map((i) => <List.Item key={i.device.id}>{i.device.name} · {i.role.title}{i.stagingId ? ' (its plan)' : ''}</List.Item>)}
          </List>
        )}
      </div>
      {waiting.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={4}>Waits</Text>
          <List size="sm" spacing={2} icon={<IconClock size={14} aria-hidden />}>
            {waiting.map((i) => <List.Item key={i.device.id}>{i.device.name}: {i.reason}</List.Item>)}
          </List>
        </div>
      )}
      <Hint>Each device gets its own plan: checked first (nothing changes), approved, then run. Runs continue on the server if you leave the page.</Hint>
      {real.length > 0
        ? <Notice kind="caution" compact title={`${real.length === 1 ? 'A real device' : `${real.length} real devices`} will be changed`}>
            {real.map((i) => i.device.name).join(', ')}: equipment on your bench, not a simulation.</Notice>
        : ready.length > 0 && <Hint>Every device here is simulated: nothing real is touched.</Hint>}
      {real.length > 0 && <SafetyHint real firmware={fwReal} />}
      <ApproveFields firmware={firmware} window={win} onWindow={setWin} maker={actor} actor={actor}
        second={second} soloOffered={offered} solo={solo} onSolo={setSolo} />
      <DialogError error={start.error} />
      <Group justify="flex-end" align="flex-start">
        <Button variant="default" onClick={onClose} data-autofocus>Cancel</Button>
        <ReasonButton color="orange" disabled={!!blocked} reason={blocked} loading={start.isPending}
          onClick={() => start.mutate(undefined)}>Start {ready.length} {ready.length === 1 ? 'device' : 'devices'}</ReasonButton>
      </Group>
    </Stack>
  );
}

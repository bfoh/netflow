import { Button, Group, List, Modal, Stack, Text } from '@mantine/core';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { Notice } from '../../components/Notice';
import { ReasonButton } from '../../components/ReasonButton';
import { SafetyHint } from '../../components/SafetyHint';
import { useAction, usePolicy } from '../../hooks/queries';
import { api, getActor } from '../../services/api';
import type { Deployment, Device } from '../../types/api';
import { ApproveFields } from '../plans/ApproveFields';
import { approveAlone, needsSecondPerson, soloOffered } from '../plans/soloApproval';
import { defaultWindow, windowBody, windowProblem } from '../plans/window';
import { stepTitle } from './staging';

/** approve: only approve (engineers, the staging page); run: it is approved, start it;
 *  both: approve and start in one confirmation (Stage a system). */
export type ApproveRunMode = 'approve' | 'run' | 'both';

const LABEL: Record<ApproveRunMode, string> = { approve: 'Approve', run: 'Run', both: 'Approve and run' };

/**
 * The one decision on a staging plan (D-121), the same in the wizard, on the staging plan page
 * and in "Check and run": what will happen, the real device named, the safety switch (with its
 * in-place turn-on), the window and who approves. The server still enforces every rule.
 */
export function ApproveRunBody({ stagingId, steps, device, mode, onDone, onCancel }: {
  stagingId: string; steps: Deployment[]; device: Device | undefined; mode: ApproveRunMode;
  onDone: () => void; onCancel: () => void;
}) {
  const policy = usePolicy();
  const p = policy.data;
  const actor = getActor();
  const approving = mode !== 'run';
  const running = mode !== 'approve';
  const firmware = steps.some((s) => s.kind === 'firmware' && s.state === 'awaiting_approval');
  const fwToRun = steps.some((s) => s.kind === 'firmware' && s.state !== 'succeeded');
  const maker = steps[0]?.created_by;
  const [win, setWin] = useState(defaultWindow);
  const [solo, setSolo] = useState(false);
  const real = !!device && device.environment !== 'simulated';
  const allowed = !real || (!!p?.enable_real_device_writes && (!fwToRun || !!p?.enable_real_device_firmware));
  const second = approving && needsSecondPerson(p, { firmware, maker, actor });
  const offered = approving && soloOffered(p, { firmware, maker, actor });
  const blocked = approving && firmware && windowProblem(win) ? 'Correct the window first.'
    : second && !(offered && solo) ? (offered ? 'Tick “I am staging alone”, or let a second person approve it.' : 'A second person must approve it.')
      : running && !allowed ? 'Turn the safety switch on first (above).'
        : null;
  const go = useAction(async () => {
    if (approving) {
      const approve = () => api.approveStaging(stagingId, firmware ? windowBody(win) : undefined);
      await (second && solo ? approveAlone(approve) : approve());
    }
    if (running) await api.executeStaging(stagingId);
  }, running ? 'Started: the steps run one after the other on the server' : 'Approved: every step can run', { errorInDialog: true });
  const todo = steps.filter((s) => s.state !== 'succeeded');
  return (
    <Stack>
      <div>
        <Text size="sm" fw={600} mb={4}>What happens</Text>
        <List size="sm" spacing={2}>{todo.map((s) => <List.Item key={s.id}>{stepTitle(s)}</List.Item>)}</List>
      </div>
      {running && (real
        ? <Notice kind="caution" compact title="A real device will be changed">{device!.name}: equipment on your bench, not a simulation.</Notice>
        : <Hint>{device?.name ?? 'This device'} is simulated: nothing real is touched.</Hint>)}
      {running && <SafetyHint real={real} firmware={fwToRun} />}
      {approving && <ApproveFields firmware={firmware} window={win} onWindow={setWin} maker={maker} actor={actor}
        second={second} soloOffered={offered} solo={solo} onSolo={setSolo} />}
      <DialogError error={go.error} />
      <Group justify="flex-end" align="flex-start">
        <Button variant="default" onClick={onCancel} data-autofocus>Cancel</Button>
        <ReasonButton color={running ? 'orange' : undefined} disabled={!!blocked} reason={blocked} loading={go.isPending}
          onClick={() => go.mutate(undefined, { onSuccess: onDone })}>{LABEL[mode]}</ReasonButton>
      </Group>
    </Stack>
  );
}

/** The decision in its own dialog. */
export function ApproveRunDialog({ opened, onClose, onDone, ...body }: {
  opened: boolean; onClose: () => void; onDone?: () => void;
  stagingId: string; steps: Deployment[]; device: Device | undefined; mode: ApproveRunMode;
}) {
  return (
    <Modal opened={opened} onClose={onClose} size="lg"
      title={`${LABEL[body.mode]}${body.device ? `: ${body.device.name}` : ''}`}>
      {opened && <ApproveRunBody {...body} onCancel={onClose} onDone={() => { onClose(); onDone?.(); }} />}
    </Modal>
  );
}

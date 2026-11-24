import { Button, Group, Modal, Stack, Text, TextInput } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconPlayerPlay, IconPlayerStop, IconShieldCheck } from '@tabler/icons-react';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { SafetyHint } from '../../components/SafetyHint';
import { useAction, useDevice, usePolicy } from '../../hooks/queries';
import { useConfirm } from '../../hooks/useConfirm';
import { api } from '../../services/api';
import type { Deployment } from '../../types/api';
import { stagingStatus } from './staging';

const toUtcInput = (d: Date) => d.toISOString().slice(0, 16);
const fromUtcInput = (v: string) => new Date(`${v}:00Z`).toISOString();

/** Approve (with a maintenance window when a firmware step waits), run and stop a staging plan. */
export function StagingControls({ stagingId, steps, onStarted, size = 'sm' }: {
  stagingId: string; steps: Deployment[]; onStarted?: () => void; size?: 'xs' | 'sm';
}) {
  const policy = usePolicy();
  const [windowOpen, { open, close }] = useDisclosure();
  const [start, setStart] = useState(() => toUtcInput(new Date(Date.now() - 5 * 60 * 1000)));
  const [end, setEnd] = useState(() => toUtcInput(new Date(Date.now() + 8 * 3600 * 1000)));
  const [ask, confirmDialog] = useConfirm();
  const firmware = steps.some((s) => s.kind === 'firmware' && s.state === 'awaiting_approval');
  const approve = useAction(() => api.approveStaging(stagingId, firmware
    ? { window_start: fromUtcInput(start), window_end: fromUtcInput(end) } : undefined), 'Approved: every step can run',
  { errorInDialog: firmware });
  const execute = useAction(() => api.executeStaging(stagingId), 'Started: the steps run one after the other on the server');
  const stop = useAction(() => api.stopStaging(stagingId), 'Stop requested: the running step ends at its next safe point',
    { errorInDialog: true });
  const s = stagingStatus(steps);
  const maker = steps[0]?.created_by;
  const second = firmware && policy.data?.firmware_require_separate_approver !== false;
  const device = useDevice(steps[0]?.targets[0]?.device_id ?? '');
  const real = !!device.data && device.data.environment !== 'simulated';
  const fwPending = steps.some((x) => x.kind === 'firmware' && x.state !== 'succeeded');
  return (
    <Stack gap={4}>
    <Group gap="xs">
      {confirmDialog}
      {s.canApprove && <Button size={size} leftSection={<IconShieldCheck size={16} />} loading={approve.isPending}
        onClick={() => (firmware ? open() : approve.mutate(undefined))}>Approve all steps</Button>}
      {s.canRun && <Button size={size} color="orange" leftSection={<IconPlayerPlay size={16} />} loading={execute.isPending}
        onClick={() => execute.mutate(undefined, { onSuccess: () => onStarted?.() })}>Run</Button>}
      {s.running && <Button size={size} color="red" variant="light" leftSection={<IconPlayerStop size={16} />} loading={stop.isPending}
        onClick={() => ask({
          title: 'Stop this staging plan?', confirmLabel: 'Stop',
          message: 'The running step ends at its next safe point and the later steps do not run. A transfer or restart the device has already begun is not undone; if the device may be half-changed, the step ends as Needs attention.',
          onConfirm: () => stop.mutateAsync(undefined),
        })}>Stop</Button>}
      <Modal opened={windowOpen} onClose={close} title="Approve all steps">
        <Stack>
          <Text size="sm">This plan upgrades firmware, which may only run inside an approved time window (at most 24 hours, times in UTC).
            {second ? ` A second person must approve it: it was made by ${maker}.` : ''}</Text>
          <TextInput type="datetime-local" label="From (UTC)" value={start} onChange={(e) => setStart(e.currentTarget.value)} />
          <TextInput type="datetime-local" label="Until (UTC)" value={end} onChange={(e) => setEnd(e.currentTarget.value)} />
          <DialogError error={approve.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Back</Button>
            <Button loading={approve.isPending} onClick={() => approve.mutate(undefined, { onSuccess: close })}>Approve</Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
    {(s.canApprove || s.canRun) && <SafetyHint real={real} firmware={fwPending} />}
    </Stack>
  );
}

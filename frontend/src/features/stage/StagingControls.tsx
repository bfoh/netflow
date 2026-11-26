import { Button, Group, Stack } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconPlayerPlay, IconPlayerStop, IconShieldCheck } from '@tabler/icons-react';
import { useState } from 'react';

import { SafetyHint } from '../../components/SafetyHint';
import { useAction, useDevice } from '../../hooks/queries';
import { useConfirm } from '../../hooks/useConfirm';
import { api } from '../../services/api';
import type { Deployment } from '../../types/api';
import { ApproveRunDialog, type ApproveRunMode } from './ApproveRun';
import { stagingStatus } from './staging';

/**
 * Approve, run and stop a staging plan (D-121). In Stage a system (`combined`) one button
 * approves and runs after one confirmation; elsewhere Approve and Run stay separate for
 * engineers. Both use the same dialog, words and window.
 */
export function StagingControls({ stagingId, steps, onStarted, size = 'sm', combined = false }: {
  stagingId: string; steps: Deployment[]; onStarted?: () => void; size?: 'xs' | 'sm'; combined?: boolean;
}) {
  const [opened, { open, close }] = useDisclosure();
  const [mode, setMode] = useState<ApproveRunMode>('run');
  const [ask, confirmDialog] = useConfirm();
  const stop = useAction(() => api.stopStaging(stagingId), 'Stop requested: the running step ends at its next safe point',
    { errorInDialog: true });
  const s = stagingStatus(steps);
  const device = useDevice(steps[0]?.targets[0]?.device_id ?? '');
  const real = !!device.data && device.data.environment !== 'simulated';
  const fwPending = steps.some((x) => x.kind === 'firmware' && x.state !== 'succeeded');
  const decide = (m: ApproveRunMode) => { setMode(m); open(); };
  return (
    <Stack gap={4}>
      <Group gap="xs">
        {confirmDialog}
        {s.canApprove && combined && <Button size={size} color="orange" leftSection={<IconPlayerPlay size={16} />}
          onClick={() => decide('both')}>Approve and run…</Button>}
        {s.canApprove && !combined && <Button size={size} leftSection={<IconShieldCheck size={16} />}
          onClick={() => decide('approve')}>Approve all steps…</Button>}
        {s.canRun && <Button size={size} color="orange" leftSection={<IconPlayerPlay size={16} />}
          onClick={() => decide('run')}>Run…</Button>}
        {s.running && <Button size={size} color="red" variant="light" leftSection={<IconPlayerStop size={16} />} loading={stop.isPending}
          onClick={() => ask({
            title: 'Stop this staging plan?', confirmLabel: 'Stop',
            message: 'The running step ends at its next safe point and the later steps do not run. A transfer or restart the device has already begun is not undone; if the device may be half-changed, the step ends as Needs attention.',
            onConfirm: () => stop.mutateAsync(undefined),
          })}>Stop</Button>}
      </Group>
      <ApproveRunDialog opened={opened} onClose={close} stagingId={stagingId} steps={steps} device={device.data} mode={mode}
        onDone={() => { if (mode !== 'approve') onStarted?.(); }} />
      {(s.canApprove || s.canRun) && !opened && <SafetyHint real={real} firmware={fwPending} />}
    </Stack>
  );
}

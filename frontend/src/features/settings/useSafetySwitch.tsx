import { Button, Checkbox, Group, Modal, Stack, Text } from '@mantine/core';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Notice } from '../../components/Notice';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import type { SafetySwitch } from '../../types/api';

export interface SwitchInfo {
  key: SafetySwitch;
  label: string;
  /** What the switch does when it is in its less safe position. */
  risky: string;
  /** What the switch is for, when that is not what its less safe position does (Settings → Safety). */
  about?: string;
  /** The less safe position: ON for the change switches, OFF for the second approver. */
  riskyValue: boolean;
  needs?: SafetySwitch;
}

export const SWITCHES: SwitchInfo[] = [
  { key: 'enable_real_device_writes', label: 'Real-device changes', riskyValue: true,
    risky: 'Approved plans may change real devices on the bench: load files, set logins, restart them.' },
  { key: 'enable_real_device_firmware', label: 'Firmware changes', riskyValue: true, needs: 'enable_real_device_writes',
    risky: 'Approved firmware plans may upgrade real devices. A device restarts into the new image.' },
  { key: 'firmware_require_separate_approver', label: 'A second person approves firmware plans', riskyValue: false,
    about: 'On: someone other than the person who made a firmware plan approves it. Turn it off only when you stage alone on the bench.',
    risky: 'The person who made a firmware plan may also approve it. Use this only when you stage alone on the bench.' },
];

/**
 * Changing a safety switch (D-082), the same way wherever it is offered: Settings → Safety,
 * or in place next to the action that needs it (D-121). The less safe direction asks first,
 * with the same tick box; the safe direction needs no confirmation. Both are audited by the
 * server.
 */
export function useSafetySwitch() {
  const [asked, setAsked] = useState<{ info: SwitchInfo; value: boolean } | null>(null);
  const [sure, setSure] = useState(false);
  const confirmed = useAction((c: Partial<Record<SafetySwitch, boolean>>) => api.changePolicy(c), 'Safety setting saved', { errorInDialog: true });
  const direct = useAction((c: Partial<Record<SafetySwitch, boolean>>) => api.changePolicy(c), 'Safety setting saved');

  const flip = (key: SafetySwitch, value: boolean) => {
    const info = SWITCHES.find((s) => s.key === key)!;
    if (value === info.riskyValue) { setSure(false); confirmed.reset(); setAsked({ info, value }); return; }
    direct.mutate({ [key]: value });
  };

  const dialog = (
    <Modal opened={!!asked} onClose={() => setAsked(null)} title={asked ? `${asked.info.label}: turn ${asked.value ? 'on' : 'off'}?` : ''}>
      {asked && (
        <Stack>
          <Notice kind="caution">{asked.info.risky}</Notice>
          <Text size="sm">Plans still need approval before they run, and you can stop a running plan. Turn this back when you have finished.</Text>
          <Checkbox label="The devices are spare units on an isolated bench" checked={sure} onChange={(e) => setSure(e.currentTarget.checked)} />
          <DialogError error={confirmed.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAsked(null)} data-autofocus>Cancel</Button>
            <Button color="red" disabled={!sure} loading={confirmed.isPending}
              onClick={() => confirmed.mutate({ [asked.info.key]: asked.value }, { onSuccess: () => setAsked(null) })}>
              Turn {asked.value ? 'on' : 'off'}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
  return { flip, dialog, pending: confirmed.isPending || direct.isPending };
}

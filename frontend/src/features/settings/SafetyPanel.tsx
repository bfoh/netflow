import { Badge, Button, Card, Checkbox, Group, Modal, Stack, Switch, Text, Title } from '@mantine/core';
import { IconLock, IconShieldCheck } from '@tabler/icons-react';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { useAction, usePolicy } from '../../hooks/queries';
import { api } from '../../services/api';
import type { Policy, SafetySwitch } from '../../types/api';
import { Notice } from '../../components/Notice';
import { Hint } from '../../components/Hint';

interface SwitchInfo {
  key: SafetySwitch;
  label: string;
  /** What the switch does when it is in its less safe position. */
  risky: string;
  /** The less safe position: ON for the change switches, OFF for the second approver. */
  riskyValue: boolean;
  needs?: SafetySwitch;
}

const SWITCHES: SwitchInfo[] = [
  { key: 'enable_real_device_writes', label: 'Real-device changes', riskyValue: true,
    risky: 'Approved plans may change real devices on the bench: load files, set logins, restart them.' },
  { key: 'enable_real_device_firmware', label: 'Firmware changes', riskyValue: true, needs: 'enable_real_device_writes',
    risky: 'Approved firmware plans may upgrade real devices. A device restarts into the new image.' },
  { key: 'firmware_require_separate_approver', label: 'A second person approves firmware plans', riskyValue: false,
    risky: 'The person who made a firmware plan may also approve it. Use this only when you stage alone on the bench.' },
];

/** Settings → Safety: the switches that let UNDM change real devices (D-082). */
export function SafetyPanel() {
  const policy = usePolicy();
  const [asked, setAsked] = useState<{ info: SwitchInfo; value: boolean } | null>(null);
  const [sure, setSure] = useState(false);
  const change = useAction((c: Partial<Record<SafetySwitch, boolean>>) => api.changePolicy(c), 'Safety setting saved', { errorInDialog: !!asked });
  const p = policy.data;
  if (!p) return null;

  const flip = (info: SwitchInfo, value: boolean) => {
    if (value === info.riskyValue) { setSure(false); setAsked({ info, value }); return; }
    change.mutate({ [info.key]: value });  // the safe direction needs no confirmation
  };

  return (
    <Stack maw={720}>
      <Hint icon={<IconShieldCheck size={14} />}>
        These switches decide whether UNDM may change <b>real</b> devices; they start off. Simulated devices can always be
        changed. Every change is recorded in the audit log and applies to this copy of UNDM only.
      </Hint>
      {SWITCHES.map((info) => {
        const on = Boolean(p[info.key as keyof Policy]);
        const locked = p.locked.includes(info.key);
        const blockedBy = info.needs && !p[info.needs] && on;
        return (
          <Card key={info.key} withBorder>
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <Stack gap={4}>
                <Group gap="xs">
                  <Title order={2}>{info.label}</Title>
                  <Badge radius="sm" variant={on === info.riskyValue ? 'filled' : 'light'} color={on === info.riskyValue ? 'red' : 'gray'}>
                    {on ? 'ON' : 'off'}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">{info.risky}</Text>
                {info.needs && <Text size="xs" c="dimmed">Works only together with Real-device changes.</Text>}
                {blockedBy && <Text size="xs" c="orange">Real-device changes are off, so this has no effect yet.</Text>}
                {locked && (
                  <Group gap={4}><IconLock size={14} /><Text size="xs">Fixed in backend\.env (<code>UNDM_{info.key.toUpperCase()}</code>). Delete that line once and restart the backend: this switch is then changed here.</Text></Group>
                )}
              </Stack>
              <Switch size="lg" checked={on} disabled={locked || change.isPending} aria-label={info.label}
                onChange={(e) => flip(info, e.currentTarget.checked)} />
            </Group>
          </Card>
        );
      })}
      <Modal opened={!!asked} onClose={() => setAsked(null)} title={asked ? `${asked.info.label}: turn ${asked.value ? 'on' : 'off'}?` : ''}>
        {asked && (
          <Stack>
            <Notice kind="caution">{asked.info.risky}</Notice>
            <Text size="sm">Plans still need approval before they run, and you can stop a running plan. Turn this back when you have finished.</Text>
            <Checkbox label="The devices are spare units on an isolated bench" checked={sure} onChange={(e) => setSure(e.currentTarget.checked)} />
            <DialogError error={change.error} />
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setAsked(null)}>Cancel</Button>
              <Button color="red" disabled={!sure} loading={change.isPending}
                onClick={() => change.mutate({ [asked.info.key]: asked.value }, { onSuccess: () => setAsked(null) })}>
                Turn {asked.value ? 'on' : 'off'}
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}

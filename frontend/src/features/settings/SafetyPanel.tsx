import { Badge, Card, Group, Stack, Switch, Text, Title } from '@mantine/core';
import { IconLock, IconShieldCheck } from '@tabler/icons-react';

import { usePolicy } from '../../hooks/queries';
import { SWITCHES, useSafetySwitch } from './useSafetySwitch';
import type { Policy } from '../../types/api';
import { Hint } from '../../components/Hint';

/** Settings → Safety: the switches that let UNDM change real devices (D-082). */
export function SafetyPanel() {
  const policy = usePolicy();
  const { flip, dialog, pending } = useSafetySwitch();
  const p = policy.data;
  if (!p) return null;

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
              <Switch size="lg" checked={on} disabled={locked || pending} aria-label={info.label}
                onChange={(e) => flip(info.key, e.currentTarget.checked)} />
            </Group>
          </Card>
        );
      })}
      {dialog}
    </Stack>
  );
}

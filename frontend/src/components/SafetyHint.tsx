import { Anchor, Button, Group, Text } from '@mantine/core';
import { IconAlertTriangle, IconLock } from '@tabler/icons-react';
import { Link } from 'react-router';

import { useSafetySwitch } from '../features/settings/useSafetySwitch';
import { usePolicy } from '../hooks/queries';
import { paths } from '../paths';

/**
 * The safety switches, shown only where they matter: next to an action on a real device
 * (D-089). Nothing is shown for simulated devices. The switch the action needs can be turned
 * on right here, with the same confirmation and audit as in Settings → Safety (D-121); a
 * switch fixed in the start-up file is changed only there.
 */
export function SafetyHint({ real, firmware = false }: { real: boolean; firmware?: boolean }) {
  const policy = usePolicy();
  const { flip, dialog, pending } = useSafetySwitch();
  if (!real || !policy.data) return null;
  const p = policy.data;
  const writes = p.enable_real_device_writes;
  const fw = p.enable_real_device_firmware;
  const allowed = writes && (!firmware || fw);
  const what = firmware ? 'Firmware changes' : 'Real-device changes';
  // The switch to turn on next: real-device changes first, then firmware changes.
  const next = !writes ? 'enable_real_device_writes' : firmware && !fw ? 'enable_real_device_firmware' : null;
  const lockedNext = next !== null && (p.locked ?? []).includes(next);
  const settings = <Anchor component={Link} to={paths.settings('safety')} size="xs">Settings → Safety</Anchor>;
  return (
    <Group gap={6} wrap="wrap" align="center">
      {dialog}
      {allowed
        ? <IconAlertTriangle size={14} color="var(--mantine-color-orange-text)" aria-hidden />
        : <IconLock size={14} color="var(--mantine-color-dimmed)" aria-hidden />}
      <Text size="xs" c={allowed ? 'var(--mantine-color-orange-text)' : 'dimmed'}>
        {allowed
          ? <>{what} are on: this can change a real device. Turn them off when you are done ({settings}).</>
          : !writes
            ? <>Real-device changes are off: real devices can only be read and dry-run.</>
            : <>Firmware changes are off: real devices get a dry run only.</>}
      </Text>
      {next && !lockedNext && (
        <Button size="compact-xs" variant="default" loading={pending} onClick={() => flip(next, true)}>
          Turn {next === 'enable_real_device_writes' ? 'real-device changes' : 'firmware changes'} on…
        </Button>
      )}
      {next && lockedNext && <Text size="xs" c="dimmed">Fixed in the start-up file: see {settings}.</Text>}
    </Group>
  );
}

/** Both switches for a place that can change settings and firmware (the bench check, a
 *  device page): the firmware line only once real-device changes are on, so a person never
 *  reads "Real-device changes are off" twice. */
export function SafetyHints({ firmware }: { firmware: boolean }) {
  const policy = usePolicy();
  return (
    <>
      <SafetyHint real />
      {firmware && policy.data?.enable_real_device_writes && <SafetyHint real firmware />}
    </>
  );
}

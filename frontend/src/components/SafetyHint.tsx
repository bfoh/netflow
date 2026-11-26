import { Anchor, Group, Text } from '@mantine/core';
import { IconAlertTriangle, IconLock } from '@tabler/icons-react';
import { Link } from 'react-router';

import { usePolicy } from '../hooks/queries';
import { paths } from '../paths';

/**
 * The safety switches, shown only where they matter: next to an action on a real device
 * (D-089). Nothing is shown for simulated devices.
 */
export function SafetyHint({ real, firmware = false }: { real: boolean; firmware?: boolean }) {
  const policy = usePolicy();
  if (!real || !policy.data) return null;
  const writes = policy.data.enable_real_device_writes;
  const fw = policy.data.enable_real_device_firmware;
  const allowed = writes && (!firmware || fw);
  const what = firmware ? 'Firmware changes' : 'Real-device changes';
  const settings = <Anchor component={Link} to={paths.settings('safety')} size="xs">Settings → Safety</Anchor>;
  return (
    <Group gap={6} wrap="nowrap" align="center">
      {allowed
        ? <IconAlertTriangle size={14} color="var(--mantine-color-orange-6)" aria-hidden />
        : <IconLock size={14} color="var(--mantine-color-dimmed)" aria-hidden />}
      <Text size="xs" c={allowed ? 'orange.8' : 'dimmed'}>
        {allowed
          ? <>{what} are on: this can change a real device. Turn them off when you are done ({settings}).</>
          : !writes
            ? <>Real-device changes are off: real devices can only be read and dry-run. Turn them on in {settings}.</>
            : <>Firmware changes are off: real devices get a dry run only. Turn them on in {settings}.</>}
      </Text>
    </Group>
  );
}

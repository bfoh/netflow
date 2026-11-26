import { Anchor, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';

import { EnvironmentBadge } from '../../components/Badges';
import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useDeviceModels, useLoginDefaults } from '../../hooks/queries';
import { paths } from '../../paths';
import { api } from '../../services/api';
import type { Device } from '../../types/api';
import { LoginSelect } from '../logins/LoginSelect';
import { deviceInputFor, type Role, type RoleKey } from './roles';

/** Which login a device of each role uses at the start of its plan. */
const LOGIN_HINT: Record<RoleKey, string> = {
  firewall: 'The approved login. On a new unit, the first login step sets it.',
  blackbox: 'New unit: admin with no password. In step 2 choose the approved login as "Login after loading".',
  aruba_a: 'The approved login. Preconfigured switch: the console setup erases it first with its current login (add that login too).',
  aruba_b: 'The approved login. Preconfigured switch: the console setup erases it first with its current login (add that login too).',
  modem: 'The approved login, user name admin: its first access gives the modem this password. The modem refuses a password it finds too simple.',
  bbu: 'No login in UNDM: UNDM never logs in to the BBU. Its portal login is typed by the person in the browser.',
};

/** One role of Stage a system step 1: its device and login, or one button that adds it with
 *  the bench defaults (D-121). */
export function RoleCard({ role, device, projectId, systemName, simulated }: {
  role: Role; device?: Device; projectId: string; systemName: string; simulated: boolean;
}) {
  const models = useDeviceModels();
  const defaults = useLoginDefaults();
  const model = models.data?.find((m) => m.model_id === role.modelId);
  const add = useAction(() => api.createDevice(projectId, deviceInputFor(role, { systemName, model, simulated, defaults: defaults.data })),
    `${role.title} added`, { errorInDialog: true });
  const setLogin = useAction((ref: string | null) => api.updateDevice(device!.id, { credential_ref_id: ref }), 'Login chosen');
  const where = device?.management_address
    || (role.consoleCable ? `console cable${device?.console_port ? ` · ${device.console_port}` : ' only'}` : '');
  return (
    <Card>
      <Group justify="space-between" wrap="nowrap" mb={4}>
        <Title order={2} size="h4">{role.title}</Title>
        {device && <EnvironmentBadge env={device.environment} />}
      </Group>
      <Text size="xs" c="dimmed" mb="xs">{role.hint}</Text>
      {device ? (
        <Stack gap={6}>
          <Group gap="xs">
            <Anchor component={Link} to={paths.device(device.id)} fw={600} size="sm">{device.name}</Anchor>
            {where && <Text size="sm" ff="monospace" c="dimmed">{where}</Text>}
          </Group>
          {role.guided
            ? <Text size="xs" c="dimmed">{LOGIN_HINT[role.key]}</Text>
            : <LoginSelect projectId={projectId} size="xs" maw={320} description={LOGIN_HINT[role.key]}
              value={device.credential_ref_id} onChange={(v) => setLogin.mutate(v)} />}
        </Stack>
      ) : (
        <Stack gap={6}>
          <Text size="sm">Not in this system yet.</Text>
          <DialogError error={add.error} />
          <Group><Button size="xs" variant="default" leftSection={<IconPlus size={14} />} loading={add.isPending} disabled={!model}
            onClick={() => add.mutate(undefined)}>Add it ({role.address || 'console cable only'})</Button></Group>
        </Stack>
      )}
    </Card>
  );
}

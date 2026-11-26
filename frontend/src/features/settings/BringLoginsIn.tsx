import { Badge, Button, Card, Group, Modal, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { IconArrowsJoin } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import type { SharedLoginGroup } from '../../types/api';
import { replaceLogins } from '../stage/choices';

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function Bring({ groups, onClose }: { groups: SharedLoginGroup[]; onClose: () => void }) {
  const [names, setNames] = useState<Record<string, string>>(() =>
    Object.fromEntries(groups.filter((g) => !g.existing).map((g) => [g.id, g.name])));
  const logins = groups.reduce((n, g) => n + g.members.length, 0);
  const run = useAction(async () => {
    const r = await api.shareLogins(names);
    replaceLogins(r.replaced);
    return r;
  }, (r) => `${plural(r.logins.length, 'login')} for all systems`, { errorInDialog: true });
  const blank = Object.values(names).some((n) => !n.trim());
  return (
    <Stack>
      <Hint>
        Each login keeps its password and the devices that use it. Logins with the same user name and password become one.
        The names are suggested from the devices that use each login and its user name: change any of them.
      </Hint>
      <Table.ScrollContainer minWidth={560}>
        <Table verticalSpacing="xs">
          <Table.Thead><Table.Tr><Table.Th>Name for all systems</Table.Th><Table.Th>From</Table.Th><Table.Th>Devices</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {groups.map((g) => (
              <Table.Tr key={g.id}>
                <Table.Td miw={260}>
                  {g.existing
                    ? <Group gap="xs"><Text size="sm">{g.name}</Text><Badge size="xs" color="gray" variant="light" tt="none">already here: joins it</Badge></Group>
                    : <TextInput size="xs" aria-label={`Name for ${g.members.map((m) => m.name).join(', ')}`} value={names[g.id] ?? ''}
                      onChange={(e) => { const v = e.currentTarget.value; setNames((n) => ({ ...n, [g.id]: v })); }} />}
                </Table.Td>
                <Table.Td>{g.members.map((m) => <Text key={m.id} size="xs">{m.name} · {m.system}</Text>)}</Table.Td>
                <Table.Td>{g.devices}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <DialogError error={run.error} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>Back</Button>
        <Button leftSection={<IconArrowsJoin size={16} />} loading={run.isPending} disabled={blank}
          onClick={() => run.mutate(undefined, { onSuccess: onClose })}>
          Bring {plural(logins, 'login')} here
        </Button>
      </Group>
    </Stack>
  );
}

/** Logins made in the systems before D-105, brought into the logins for all systems (D-115). */
export function BringLoginsIn() {
  const groups = useQuery({ queryKey: ['logins-from-systems'], queryFn: api.loginsFromSystems });
  const [open, setOpen] = useState(false);
  const list = groups.data ?? [];
  if (!list.length) return null;
  const logins = list.reduce((n, g) => n + g.members.length, 0);
  const systems = new Set(list.flatMap((g) => g.members.map((m) => m.system))).size;
  return (
    <Card withBorder>
      <Title order={2} size="h5" mb={4}>Logins made in the systems</Title>
      <Text size="sm" mb="sm">
        {plural(systems, 'system')} still {systems === 1 ? 'has' : 'have'} {plural(logins, 'login')} of {systems === 1 ? 'its' : 'their'} own.
        Bring them here so every system can use them.
      </Text>
      <Group><Button variant="light" leftSection={<IconArrowsJoin size={16} />} onClick={() => setOpen(true)}>Bring them here…</Button></Group>
      <Modal opened={open} onClose={() => setOpen(false)} title="Bring the systems' logins here" size="xl">
        {open && <Bring groups={list} onClose={() => setOpen(false)} />}
      </Modal>
    </Card>
  );
}

import { ActionIcon, Alert, Badge, Button, Card, Checkbox, Group, Modal, PasswordInput, Stack, Table, Text, TextInput, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconKey, IconPlus, IconShieldLock, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';

import { useAction, useCredentialRefs } from '../../hooks/queries';
import { api } from '../../services/api';
import type { CredentialRef } from '../../types/api';

/** Username/password entry. The password goes straight to the backend, which writes it to
 *  the OS credential store; it is never shown again or stored in the UNDM database. */
function SecretForm({ onSubmit, busy, submitLabel }:
  { onSubmit: (u: string, p: string) => void; busy: boolean; submitLabel: string }) {
  const [u, setU] = useState('');
  const [p, setP] = useState('');
  const [none, setNone] = useState(false);
  return (
    <Stack>
      <TextInput label="Device username" value={u} onChange={(e) => setU(e.currentTarget.value)} autoComplete="off" />
      <PasswordInput label="Device password" value={none ? '' : p} disabled={none} onChange={(e) => setP(e.currentTarget.value)} autoComplete="new-password" />
      <Checkbox label="No password (factory-default device)" checked={none} onChange={(e) => setNone(e.currentTarget.checked)} />
      <Button onClick={() => onSubmit(u, none ? '' : p)} loading={busy} disabled={!u || (!p && !none)}>{submitLabel}</Button>
    </Stack>
  );
}

export function CredentialsPanel({ projectId }: { projectId: string }) {
  const refs = useCredentialRefs(projectId);
  const [opened, { open, close }] = useDisclosure();
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<CredentialRef | null>(null);
  const create = useAction(async ({ u, p }: { u: string; p: string }) => {
    const ref = await api.createCredentialRef(projectId, { name, provider: 'keyring' });
    try {
      return await api.setCredentialSecret(ref.id, u, p);
    } catch (e) {
      await api.deleteCredentialRef(ref.id); // do not leave an empty reference behind
      throw e;
    }
  }, 'Login stored in Windows Credential Manager');
  const update = useAction(({ id, u, p }: { id: string; u: string; p: string }) => api.setCredentialSecret(id, u, p), 'Password updated');
  const del = useAction((id: string) => api.deleteCredentialRef(id), 'Login deleted');

  return (
    <Stack>
      <Alert color="blue" icon={<IconShieldLock size={18} />}>
        A login is a user name and password for a device. Passwords are kept in your Windows Credential Manager, not in UNDM,
        and cannot be viewed again here. Choose a device's login on its <b>Edit device</b> form.
      </Alert>
      <Group><Button leftSection={<IconPlus size={16} />} onClick={() => { setName(''); open(); }}>Add login</Button></Group>
      <Card withBorder padding={0}>
        <Table verticalSpacing="xs" horizontalSpacing="md">
          <Table.Thead><Table.Tr><Table.Th>Name</Table.Th><Table.Th>Stored in</Table.Th><Table.Th>Password set</Table.Th><Table.Th w={110} /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {(refs.data ?? []).map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td>{r.name}</Table.Td>
                <Table.Td>{r.provider === 'keyring' ? 'Credential Manager' : `environment (${r.locator})`}</Table.Td>
                <Table.Td>{r.has_secret === null ? <Badge color="yellow" variant="light">store unavailable</Badge>
                  : r.has_secret ? <Badge color="teal" variant="light">yes</Badge> : <Badge color="gray" variant="light">no</Badge>}</Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    {r.provider === 'keyring' && <Tooltip label="Set username/password"><ActionIcon variant="subtle" aria-label={`Set password for ${r.name}`} onClick={() => setEditing(r)}><IconKey size={16} /></ActionIcon></Tooltip>}
                    <Tooltip label="Delete"><ActionIcon variant="subtle" color="red" aria-label={`Delete ${r.name}`}
                      onClick={() => { if (window.confirm(`Delete login "${r.name}"? Devices using it lose their login.`)) del.mutate(r.id); }}><IconTrash size={16} /></ActionIcon></Tooltip>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {refs.data?.length === 0 && <Table.Tr><Table.Td colSpan={4}><Text c="dimmed" ta="center" p="md">No logins yet. Add the factory login and your approved login.</Text></Table.Td></Table.Tr>}
          </Table.Tbody>
        </Table>
      </Card>
      <Modal opened={opened} onClose={close} title="Add login">
        <Stack>
          <TextInput label="Name" placeholder="e.g. switch approved login" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          {name.trim() && <SecretForm busy={create.isPending} submitLabel="Store login"
            onSubmit={(u, p) => create.mutate({ u, p }, { onSuccess: close })} />}
        </Stack>
      </Modal>
      <Modal opened={!!editing} onClose={() => setEditing(null)} title={`Set password: ${editing?.name ?? ''}`}>
        {editing && <SecretForm busy={update.isPending} submitLabel="Update"
          onSubmit={(u, p) => update.mutate({ id: editing.id, u, p }, { onSuccess: () => setEditing(null) })} />}
      </Modal>
    </Stack>
  );
}

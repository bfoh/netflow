import { StagedBadge } from '../features/systems/StagedBadge';
import { ActionIcon, Anchor, Button, Card, Modal, Stack, Table, Text, TextInput, Textarea, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { DialogError } from '../components/ConfirmDialog';
import { ImportSystemButton } from '../features/systems/SystemPackage';
import { useConfirm } from '../hooks/useConfirm';
import { useAction, useAllDevices, useProjects } from '../hooks/queries';
import { api } from '../services/api';
import { paths } from '../paths';

export function ProjectsPage() {
  const projects = useProjects();
  const devices = useAllDevices();
  const [opened, { open, close }] = useDisclosure();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', description: '', site: '', purpose: '' });
  const create = useAction(api.createProject, 'System created', { errorInDialog: true });
  const del = useAction((id: string) => api.deleteProject(id), 'System deleted', { errorInDialog: true });
  const [ask, confirmDialog] = useConfirm();

  const submit = () =>
    create.mutate(form, {
      onSuccess: (p) => { close(); setForm({ name: '', description: '', site: '', purpose: '' }); void navigate(paths.system(p.id)); },
    });

  return (
    <>
      <PageHeader
        title="Systems"
        description="A system is the set of devices you stage together, with their files, logins and plans."
        actions={<><ImportSystemButton /><Button leftSection={<IconPlus size={16} />} onClick={open}>New system</Button></>}
      />
      <QueryState isLoading={projects.isLoading} error={projects.error} />
      {confirmDialog}
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={600}>
          <Table highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
            <Table.Thead><Table.Tr><Table.Th>Name</Table.Th><Table.Th>Site</Table.Th><Table.Th>Purpose</Table.Th><Table.Th>Devices</Table.Th><Table.Th>Updated</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {(projects.data ?? []).map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td><Anchor component={Link} to={paths.system(p.id)} fw={600}>{p.name}</Anchor> <StagedBadge project={p} /></Table.Td>
                  <Table.Td>{p.site || '—'}</Table.Td>
                  <Table.Td>{p.purpose || '—'}</Table.Td>
                  <Table.Td>{(devices.data ?? []).filter((d) => d.project_id === p.id).length}</Table.Td>
                  <Table.Td>{fmtDate(p.updated_at)}</Table.Td>
                  <Table.Td><Tooltip label="Delete system"><ActionIcon variant="subtle" color="red" aria-label={`Delete ${p.name}`}
                    onClick={() => ask({
                      title: `Delete system "${p.name}"?`, confirmLabel: 'Delete system', typed: p.name,
                      message: 'Its devices, files, logins (with their passwords in Credential Manager), plans and their history are removed from UNDM. The devices themselves are not touched.',
                      onConfirm: () => del.mutateAsync(p.id),
                    })}><IconTrash size={16} /></ActionIcon></Tooltip></Table.Td>
                </Table.Tr>
              ))}
              {projects.data?.length === 0 && (
                <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" p="md">No systems yet. A system is the set of devices you stage together: create one with New system.</Text></Table.Td></Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <Modal opened={opened} onClose={close} title="New system">
        <Stack>
          <TextInput label="System name" required value={form.name} data-autofocus
            onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
          <TextInput label="Site or location" value={form.site}
            onChange={(e) => setForm({ ...form, site: e.currentTarget.value })} />
          <TextInput label="Purpose" value={form.purpose}
            onChange={(e) => setForm({ ...form, purpose: e.currentTarget.value })} />
          <Textarea label="Description" autosize minRows={2} value={form.description}
            onChange={(e) => setForm({ ...form, description: e.currentTarget.value })} />
          <DialogError error={create.error} />
          <Button onClick={submit} loading={create.isPending} disabled={!form.name.trim()}>Create system</Button>
        </Stack>
      </Modal>
    </>
  );
}

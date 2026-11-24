import { Anchor, Button, Card, Group, SimpleGrid, Stack, Table, Tabs, Text, Textarea, TextInput, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate, planKind } from '../services/format';
import { AddDeviceModal } from '../features/devices/AddDeviceModal';
import { CredentialsPanel } from '../features/devices/CredentialsPanel';
import { DeviceTable } from '../features/devices/DeviceTable';
import { useAction, useDeployments, useProject, useProjectDevices } from '../hooks/queries';
import { api } from '../services/api';
import type { CertificateSubject, Project } from '../types/api';

function ProjectSettings({ project }: { project: Project }) {
  const [form, setForm] = useState(project);
  const save = useAction((p: Partial<Project>) => api.updateProject(project.id, p), 'Project saved');
  const del = useAction(() => api.deleteProject(project.id), 'Project deleted');
  const navigate = useNavigate();
  return (
    <Card withBorder maw={640}>
      <Stack>
        <TextInput label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
        <TextInput label="Site or location" value={form.site} onChange={(e) => setForm({ ...form, site: e.currentTarget.value })} />
        <TextInput label="Network purpose" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.currentTarget.value })} />
        <Textarea label="Description" autosize minRows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.currentTarget.value })} />
        <Group justify="space-between">
          <Button color="red" variant="subtle" loading={del.isPending}
            onClick={() => { if (window.confirm(`Delete project "${project.name}" and all its devices and history?`)) del.mutate(undefined, { onSuccess: () => void navigate('/projects') }); }}>
            Delete project
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate({ name: form.name, site: form.site, purpose: form.purpose, description: form.description })}>Save</Button>
        </Group>
      </Stack>
    </Card>
  );
}

const EMPTY_SUBJECT: CertificateSubject = {
  common_name: '', org_unit: '', org_name: '', locality: '', state: '', country: '',
  profile_name: 'Profile', certificate_name: 'certificate',
};

/** Answers UNDM gives to the 2930F's certificate questions before loading an HTTPS-only file. */
function CertificateSettings({ project }: { project: Project }) {
  const [form, setForm] = useState<CertificateSubject>(project.certificate_subject ?? EMPTY_SUBJECT);
  const save = useAction((subject: CertificateSubject | null) =>
    api.updateProject(project.id, { certificate_subject: subject }), 'Certificate subject saved');
  const field = (key: keyof CertificateSubject, label: string, extra: Record<string, unknown> = {}) => (
    <TextInput label={label} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.currentTarget.value })} {...extra} />
  );
  return (
    <Card withBorder maw={640}>
      <Stack>
        <Title order={5}>HTTPS certificate (Aruba 2930F)</Title>
        <Text size="sm" c="dimmed">
          Before loading a 2930F file that makes the web interface HTTPS-only, UNDM creates the self-signed certificate with
          your team's commands and answers the switch's questions with these values. They are stored only in this UNDM
          database. Leave empty to create the certificate by hand.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {field('common_name', 'Common Name (CN)', { required: true })}
          {field('org_unit', 'Org Unit (OU)')}
          {field('org_name', 'Org Name (O)')}
          {field('locality', 'Locality (L)')}
          {field('state', 'State (ST)')}
          {field('country', 'Country (C)', { description: 'Two letters, or empty', maxLength: 2 })}
          {field('profile_name', 'Identity profile name')}
          {field('certificate_name', 'Certificate name')}
        </SimpleGrid>
        <Group justify="space-between">
          <Button variant="subtle" color="red" disabled={!project.certificate_subject} loading={save.isPending}
            onClick={() => save.mutate(null)}>Remove</Button>
          <Button loading={save.isPending} disabled={!form.common_name.trim()} onClick={() => save.mutate(form)}>Save certificate subject</Button>
        </Group>
      </Stack>
    </Card>
  );
}

export function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const project = useProject(projectId);
  const devices = useProjectDevices(projectId);
  const deployments = useDeployments(projectId);
  const [opened, { open, close }] = useDisclosure();

  if (!project.data) return <QueryState isLoading={project.isLoading} error={project.error} />;
  const p = project.data;
  return (
    <>
      <PageHeader title={p.name} description={[p.site, p.purpose].filter(Boolean).join(' · ') || 'No site or purpose recorded'}
        actions={<Button leftSection={<IconPlus size={16} />} onClick={open}>Add device</Button>} />
      <Tabs defaultValue="devices" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="devices">Network elements ({devices.data?.length ?? 0})</Tabs.Tab>
          <Tabs.Tab value="deployments">Deployments ({deployments.data?.length ?? 0})</Tabs.Tab>
          <Tabs.Tab value="credentials">Credentials</Tabs.Tab>
          <Tabs.Tab value="settings">Project settings</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="devices">
          <QueryState isLoading={devices.isLoading} error={devices.error} />
          <DeviceTable devices={devices.data ?? []} />
        </Tabs.Panel>
        <Tabs.Panel value="deployments">
          <Card withBorder padding={0}>
            <Table verticalSpacing="xs" horizontalSpacing="md">
              <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>Type</Table.Th><Table.Th>Created by</Table.Th><Table.Th>Approved by</Table.Th><Table.Th>State</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(deployments.data ?? []).map((d) => (
                  <Table.Tr key={d.id}>
                    <Table.Td><Anchor component={Link} to={`/deployments/${d.id}`}>{fmtDate(d.created_at)}</Anchor></Table.Td>
                    <Table.Td>{planKind(d)}</Table.Td>
                    <Table.Td>{d.created_by}</Table.Td><Table.Td>{d.approved_by ?? '—'}</Table.Td>
                    <Table.Td><StateBadge state={d.state} /></Table.Td>
                  </Table.Tr>
                ))}
                {deployments.data?.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" ta="center" p="md">No deployments yet.</Text></Table.Td></Table.Tr>}
              </Table.Tbody>
            </Table>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="credentials"><CredentialsPanel projectId={projectId} /></Tabs.Panel>
        <Tabs.Panel value="settings">
          <SimpleGrid cols={1}>
            <ProjectSettings key={p.updated_at} project={p} />
            <CertificateSettings key={`cert-${p.updated_at}`} project={p} />
            <Title order={6} c="dimmed">Created {fmtDate(p.created_at)} · updated {fmtDate(p.updated_at)}</Title>
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>
      <AddDeviceModal projectId={projectId} opened={opened} onClose={close} />
    </>
  );
}

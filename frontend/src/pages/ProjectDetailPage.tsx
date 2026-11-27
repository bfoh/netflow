import { ActionIcon, Anchor, Button, Card, Grid, Group, Menu, SegmentedControl, SimpleGrid, Stack, Switch, Table, Tabs, Text, TextInput, Textarea, Title, Tooltip } from '@mantine/core';
import { InlineStatus } from '../components/InlineStatus';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconFileText, IconListCheck, IconPlus, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';

import { PageHeader, QueryState } from '../components/Page';
import { PlanStatus } from '../features/plans/AttentionBadge';
import { usePlanDelete } from '../hooks/usePlanDelete';
import { fmtDate, planKind } from '../services/format';
import { AddDeviceModal } from '../features/devices/AddDeviceModal';
import { CredentialsPanel } from '../features/devices/CredentialsPanel';
import { DeviceTable } from '../features/devices/DeviceTable';
import { BenchLogDialog } from '../features/systems/BenchLogButton';
import { NetworkTab } from '../features/network/NetworkTab';
import { SystemTree } from '../features/systems/SystemTree';
import { StagedBadge } from '../features/systems/StagedBadge';
import { DownloadBackupsDialog, ExportSystemDialog } from '../features/systems/SystemPackage';
import { useConfirm } from '../hooks/useConfirm';
import { useAction, useDeployments, useProject, useProjectDevices, useReachability, useSharedCertificate } from '../hooks/queries';
import { CertificateForm } from '../features/settings/CertificateForm';
import { api } from '../services/api';
import type { CertificateSubject, Project } from '../types/api';
import { paths } from '../paths';

function ProjectSettings({ project }: { project: Project }) {
  const [form, setForm] = useState(project);
  const save = useAction((p: Partial<Project>) => api.updateProject(project.id, p), 'System saved');
  const del = useAction(() => api.deleteProject(project.id), 'System deleted', { errorInDialog: true });
  const navigate = useNavigate();
  const [ask, confirmDialog] = useConfirm();
  return (
    <Card withBorder maw={640}>
      {confirmDialog}
      <Stack>
        <TextInput label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
        <TextInput label="Site or location" value={form.site} onChange={(e) => setForm({ ...form, site: e.currentTarget.value })} />
        <TextInput label="Purpose" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.currentTarget.value })} />
        <Textarea label="Description" autosize minRows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.currentTarget.value })} />
        <Group justify="space-between">
          <Button color="red" variant="subtle" loading={del.isPending}
            onClick={() => ask({
              title: `Delete system "${project.name}"?`, confirmLabel: 'Delete system', typed: project.name,
              message: 'Its devices, files, logins (with their passwords in Credential Manager), plans and their history are removed from UNDM. The devices themselves are not touched.',
              onConfirm: async () => { await del.mutateAsync(); void navigate(paths.systems); } })}>
            Delete system
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate({ name: form.name, site: form.site, purpose: form.purpose, description: form.description })}>Save</Button>
        </Group>
      </Stack>
    </Card>
  );
}

/** The 2930F certificate answers: those for all systems, or this system's own (D-105). */
function CertificateSettings({ project }: { project: Project }) {
  const shared = useSharedCertificate();
  const [override, setOverride] = useState(!!project.certificate_subject);
  const save = useAction((subject: CertificateSubject | null) =>
    api.updateProject(project.id, { certificate_subject: subject }), (r) => (r.certificate_subject ? 'Certificate answers saved for this system' : 'This system uses the answers for all systems'));
  const own = !!project.certificate_subject;
  return (
    <Card withBorder maw={640}>
      <Stack>
        <Title order={2}>HTTPS certificate (Aruba 2930F)</Title>
        <Text size="sm" c="dimmed">
          Before loading a 2930F file that makes the web interface HTTPS-only, UNDM creates the self-signed certificate with
          your team's commands and answers the switch's questions. The answers are set once in{' '}
          <Anchor component={Link} to={paths.settings('certificate')} size="sm">Settings → Certificate</Anchor>.
        </Text>
        {own ? (
          <Text size="sm">This system uses its own answers (common name <b>{project.certificate_subject!.common_name}</b>).</Text>
        ) : shared.data?.subject ? (
          <Text size="sm">This system uses the answers for all systems (common name <b>{shared.data.subject.common_name}</b>).</Text>
        ) : (
          <InlineStatus tone="warning" size="sm">No answers are set for all systems yet: a 2930F file that needs the certificate cannot be loaded.</InlineStatus>
        )}
        <Switch label="Different answers for this system" checked={override || own}
          onChange={(e) => { const on = e.currentTarget.checked; setOverride(on); if (!on && own) save.mutate(null); }} />
        {(override || own) && (
          <CertificateForm value={project.certificate_subject ?? shared.data?.subject ?? null} saving={save.isPending}
            onSave={(s) => { if (s === null) setOverride(false); save.mutate(s); }}
            saveLabel="Save for this system" removeLabel="Use the answers for all systems" />
        )}
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
  const [benchOpen, bench] = useDisclosure();
  const [backupsOpen, backups] = useDisclosure();
  const [exportOpen, exportIt] = useDisclosure();
  const dialogs = { bench: { opened: benchOpen, ...bench }, backups: { opened: backupsOpen, ...backups }, export: { opened: exportOpen, ...exportIt } };
  const [askToDelete, deleteDialog, canDelete] = usePlanDelete();
  const [selected, setSelected] = useState<string[]>([]);
  const [watch, setWatch] = useWatch(projectId);
  const [view, setView] = useView();
  const reach = useReachability(projectId, watch);
  const reachMap = new Map((reach.data ?? []).map((r) => [r.device_id, r.state]));
  const [params, setParams] = useSearchParams();
  // Tab names before D-120 still open the right tab.
  const raw = params.get('tab') ?? 'devices';
  const tab = ({ deployments: 'plans', credentials: 'logins' } as Record<string, string>)[raw] ?? raw;

  if (!project.data) return <QueryState isLoading={project.isLoading} error={project.error} />;
  const p = project.data;
  return (
    <>
      <PageHeader title={p.name} breadcrumbs={[{ label: 'Systems', to: paths.systems }]}
        description={[p.site, p.purpose].filter(Boolean).join(' · ') || undefined}
        badges={<StagedBadge project={p} />}
        primary={<Button component={Link} to={paths.stage(projectId)} leftSection={<IconListCheck size={16} />}>Stage this system</Button>}
        secondary={<Button variant="default" leftSection={<IconPlus size={16} />} onClick={open}>Add device</Button>}
        menu={<>
          <Menu.Item leftSection={<IconFileText size={14} />} onClick={dialogs.bench.open}>Bench log…</Menu.Item>
          <Menu.Item leftSection={<IconDownload size={14} />} onClick={dialogs.backups.open}>Download backups…</Menu.Item>
          <Menu.Item leftSection={<IconDownload size={14} />} onClick={dialogs.export.open}>Export the system…</Menu.Item>
        </>} />
      <BenchLogDialog projectId={projectId} opened={dialogs.bench.opened} onClose={dialogs.bench.close} />
      <DownloadBackupsDialog projectId={projectId} opened={dialogs.backups.opened} onClose={dialogs.backups.close} />
      <ExportSystemDialog projectId={projectId} opened={dialogs.export.opened} onClose={dialogs.export.close} />
      <Tabs value={tab} onChange={(v) => setParams(v && v !== 'devices' ? { tab: v } : {}, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="devices">Devices ({devices.data?.length ?? 0})</Tabs.Tab>
          <Tabs.Tab value="network">In the network{p.reached_via === 'network' ? ' (now)' : ''}</Tabs.Tab>
          <Tabs.Tab value="plans">Plans ({deployments.data?.length ?? 0})</Tabs.Tab>
          <Tabs.Tab value="logins">Logins</Tabs.Tab>
          <Tabs.Tab value="settings">System settings</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="devices">
          <QueryState isLoading={devices.isLoading} error={devices.error} />
          <Group justify="space-between" mb="xs" wrap="wrap">
            <SegmentedControl size="xs" aria-label="Show the devices as" value={view} onChange={(v) => setView(v === 'tree' ? 'tree' : 'table')}
              data={[{ value: 'table', label: 'Table' }, { value: 'tree', label: 'Table and tree' }]} />
            <Switch size="sm" label="Watch devices (checks every 15 s whether each answers)" checked={watch}
              onChange={(e) => setWatch(e.currentTarget.checked)} />
          </Group>
          {view === 'tree' ? (
            <Grid>
              <Grid.Col span={{ base: 12, lg: 3 }}>
                <SystemTree name={p.name} devices={devices.data ?? []} selected={selected} onSelectedChange={setSelected}
                  reach={watch ? reachMap : undefined} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, lg: 9 }}>
                <DeviceTable devices={devices.data ?? []} selected={selected} onSelectedChange={setSelected}
                  reach={watch ? reachMap : undefined} />
              </Grid.Col>
            </Grid>
          ) : <DeviceTable devices={devices.data ?? []} selected={selected} onSelectedChange={setSelected}
            reach={watch ? reachMap : undefined} />}
        </Tabs.Panel>
        <Tabs.Panel value="network"><NetworkTab project={p} devices={devices.data ?? []} /></Tabs.Panel>
        <Tabs.Panel value="plans">
          {deleteDialog}
          <Card withBorder padding={0}>
            <Table.ScrollContainer minWidth={560}>
              <Table aria-label="Plans of this system" verticalSpacing="xs" horizontalSpacing="md">
                <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>Type</Table.Th><Table.Th>Created by</Table.Th><Table.Th>Approved by</Table.Th><Table.Th>Status</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {(deployments.data ?? []).map((d) => (
                    <Table.Tr key={d.id}>
                      <Table.Td><Anchor component={Link} to={paths.plan(d.id)}>{fmtDate(d.created_at)}</Anchor></Table.Td>
                      <Table.Td>{planKind(d)}</Table.Td>
                      <Table.Td>{d.created_by}</Table.Td><Table.Td>{d.approved_by ?? '—'}</Table.Td>
                      <Table.Td><PlanStatus d={d} /></Table.Td>
                      <Table.Td>{canDelete(d) && <Tooltip label="Delete plan"><ActionIcon variant="subtle" color="red" aria-label={`Delete plan of ${fmtDate(d.created_at)}`}
                      onClick={() => askToDelete(d)}><IconTrash size={16} /></ActionIcon></Tooltip>}</Table.Td>
                    </Table.Tr>
                  ))}
                  {deployments.data?.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" p="md">No plans yet. Stage this system to make them.</Text></Table.Td></Table.Tr>}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="logins"><CredentialsPanel projectId={projectId} /></Tabs.Panel>
        <Tabs.Panel value="settings">
          <SimpleGrid cols={1}>
            <ProjectSettings key={p.updated_at} project={p} />
            <CertificateSettings key={`cert-${p.updated_at}`} project={p} />
            <Text size="xs" c="dimmed">Created {fmtDate(p.created_at)} · updated {fmtDate(p.updated_at)}</Text>
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>
      <AddDeviceModal projectId={projectId} opened={opened} onClose={close} />
    </>
  );
}

/** Table or tree, remembered in this browser for every system (D-122). */
function useView(): ['table' | 'tree', (v: 'table' | 'tree') => void] {
  const KEY = 'undm.system.view';
  const [view, setState] = useState<'table' | 'tree'>(() => {
    try { return window.localStorage.getItem(KEY) === 'tree' ? 'tree' : 'table'; } catch { return 'table'; }
  });
  const set = (v: 'table' | 'tree') => {
    setState(v);
    try { window.localStorage.setItem(KEY, v); } catch { /* not remembered: still works */ }
  };
  return [view, set];
}

/** The "Watch devices" switch, remembered per system in this browser (D-099). */
function useWatch(projectId: string): [boolean, (on: boolean) => void] {
  const key = `undm.watch.${projectId}`;
  const [on, setOn] = useState(() => {
    try { return window.localStorage.getItem(key) === '1'; } catch { return false; }
  });
  return [on, (v: boolean) => {
    setOn(v);
    try { window.localStorage.setItem(key, v ? '1' : '0'); } catch { /* storage unavailable */ }
  }];
}


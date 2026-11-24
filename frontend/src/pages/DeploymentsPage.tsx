import { ActionIcon, Alert, Anchor, Button, Card, Checkbox, Group, SegmentedControl, Select, Stack, Switch, Table, Text, Title, Tooltip } from '@mantine/core';
import { IconInfoCircle, IconTrash } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { PlanStatus } from '../features/plans/AttentionBadge';
import { usePlanDelete } from '../hooks/usePlanDelete';
import { fmtDate, planKind } from '../services/format';
import { useAction, useAllDeployments, useConfig, useConfigs, useCredentialRefs, useProjectDevices, useProjects } from '../hooks/queries';
import type { ConfigVersion } from '../types/api';

const versionLabel = (v: ConfigVersion) =>
  `${v.kind}${v.reference ? ` · ${v.reference}` : ''} · ${fmtDate(v.created_at)} · ${v.sha256.slice(0, 8)}`;

/** Which configuration version a plan deploys to one device; starts with the latest generated
 *  file, else the latest imported one (what UNDM would take), so its needs are always shown. */
function ConfigChoice({ deviceId, value, onChange }: { deviceId: string; value: string | null; onChange: (v: string) => void }) {
  const configs = useConfigs(deviceId);
  const versions = (configs.data ?? []).filter((v) => v.kind !== 'backup');
  const fallback = versions.find((v) => v.kind === 'generated') ?? versions.find((v) => v.kind === 'imported');
  useEffect(() => { if (!value && fallback) onChange(fallback.id); }, [value, fallback, onChange]);
  if (configs.data && versions.length === 0) {
    return <Text size="xs" c="orange">No file yet: import one (Files page) or generate one from its settings.</Text>;
  }
  return <Select size="xs" w="100%" maw={320} aria-label="Configuration to deploy" placeholder="Choose the file"
    data={versions.map((v) => ({ value: v.id, label: versionLabel(v) }))} value={value}
    onChange={(v) => { if (v) onChange(v); }} allowDeselect={false} />;
}
import { api } from '../services/api';
import { applyModeLabel, stateLabel } from '../services/labels';

/**
 * What the chosen file needs: the apply mode its kind requires, and a credential for each
 * secret setting (e.g. a tunnel pre-shared key). Values never pass through the browser.
 */
function FileNeeds({ projectId, versionId, secrets, onSecrets, onMode, loginAfter, onLoginAfter }: {
  projectId: string; versionId: string; secrets: Record<string, string>;
  onSecrets: (s: Record<string, string>) => void; onMode: (m: string) => void;
  loginAfter: string | null; onLoginAfter: (v: string | null) => void;
}) {
  const version = useConfig(versionId);
  const refs = useCredentialRefs(projectId);
  const report = version.data?.inspection;
  const mode = report?.apply_mode;
  useEffect(() => { if (mode) onMode(mode); }, [mode, onMode]);
  if (!report) return null;
  return (
    <Stack gap={4} mt={4}>
      <Text size="xs" c={report.blocked_reason || report.problems.length ? 'red' : 'dimmed'}>
        {report.summary}{mode ? ` → loaded as ${applyModeLabel(mode)}` : ''}{report.blocked_reason ? `. ${report.blocked_reason}` : ''}
      </Text>
      {(report.secret_slots ?? []).map((slot) => (
        <Select key={slot.slot_id} size="xs" w="100%" maw={320} clearable
          label={`Value for ${slot.setting} (line ${slot.line})`}
          description={secrets[slot.slot_id] ? 'Sent from Windows Credential Manager; never shown or stored with the plan.' : 'Not set: the value written in the file is sent.'}
          placeholder={refs.data?.length ? 'Choose a login' : 'Add one on the system\'s Logins tab'}
          data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))}
          value={secrets[slot.slot_id] ?? null}
          onChange={(v) => {
            const next = { ...secrets };
            if (v) next[slot.slot_id] = v; else delete next[slot.slot_id];
            onSecrets(next);
          }} />
      ))}
      {report.apply_mode === 'replace' && (
        <Select size="xs" w="100%" maw={320} clearable label="Login after loading (optional)"
          description={loginAfter
            ? 'UNDM logs in with this after the restart and keeps it for the device. If the unit then demands a new password, UNDM sets the device\'s current (approved) login where it knows the questions (FortiGate), otherwise it waits for you to set it by hand; the device then keeps its current login.'
            : 'Choose it if the file changes the login (2930F files: the approved password; FortiGate base file: the password it sets).'}
          placeholder={refs.data?.length ? 'Same login as now' : 'Add one on the system\'s Logins tab'}
          data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))}
          value={loginAfter} onChange={onLoginAfter} />
      )}
    </Stack>
  );
}

function NewPlan({ projectId, preselected, version }: { projectId: string; preselected: string[]; version: string | null }) {
  const devices = useProjectDevices(projectId);
  const [sel, setSel] = useState<string[]>(preselected);
  const [dryRun, setDryRun] = useState(false);
  const [mode, setMode] = useState('merge');
  // The mode each chosen file requires by its kind (complete file → replace, script → merge).
  const [fileModes, setFileModes] = useState<Record<string, string>>({});
  // Opened from "Deploy this version…": that version is chosen for its device.
  const [choice, setChoice] = useState<Record<string, string>>(
    () => (version && preselected.length === 1 ? { [preselected[0]]: version } : {}));
  const [secrets, setSecrets] = useState<Record<string, Record<string, string>>>({});
  const [loginAfter, setLoginAfter] = useState<Record<string, string>>({});
  const navigate = useNavigate();
  const chosen = Object.fromEntries(
    Object.entries(choice).filter(([id]) => sel.includes(id)));
  const required = [...new Set(sel.filter((id) => chosen[id] && fileModes[id]).map((id) => fileModes[id]))];
  const forced = required.length === 1 ? required[0] : null;
  const effectiveMode = forced ?? mode;
  const chosenLogins = Object.fromEntries(Object.entries(loginAfter).filter(([id]) => id in chosen));
  const chosenSecrets = Object.fromEntries(
    Object.entries(secrets).filter(([id, s]) => id in chosen && Object.keys(s).length));
  const create = useAction(() => api.createDeployment(projectId, {
    device_ids: sel, dry_run: dryRun, apply_mode: effectiveMode,
    config_versions: Object.keys(chosen).length ? chosen : undefined,
    secrets: Object.keys(chosenSecrets).length ? chosenSecrets : undefined,
    credentials_after: Object.keys(chosenLogins).length ? chosenLogins : undefined,
  }),
    (d) => `Plan created: ${stateLabel(d.state).toLowerCase()}`);

  return (
    <Card withBorder>
      <Title order={2} size="h4" mb="xs">New configuration plan</Title>
      <Text size="sm" c="dimmed" mb="md">
        Tick the devices and choose the file each one gets (it starts with the latest generated file, else the latest
        imported one). The plan is checked and previewed against each device; it then needs approval before it runs. A dry
        run only reads from the devices.
      </Text>
      <QueryState isLoading={devices.isLoading} error={devices.error} />
      <Table.ScrollContainer minWidth={760}>
      <Table verticalSpacing={4} mb="md">
        <Table.Thead><Table.Tr><Table.Th w={36} /><Table.Th>Device</Table.Th><Table.Th>Model</Table.Th><Table.Th>Kind</Table.Th><Table.Th>Status</Table.Th><Table.Th>File to load</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {(devices.data ?? []).map((d) => (
            <Table.Tr key={d.id}>
              <Table.Td w={36}><Checkbox aria-label={`Include ${d.name}`} checked={sel.includes(d.id)}
                onChange={() => setSel((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id]))} /></Table.Td>
              <Table.Td>{d.name}</Table.Td><Table.Td>{d.manufacturer} {d.model}</Table.Td>
              <Table.Td><EnvironmentBadge env={d.environment} /></Table.Td><Table.Td><StateBadge state={d.deployment_status} /></Table.Td>
              <Table.Td>{sel.includes(d.id) && (
                <>
                  <ConfigChoice deviceId={d.id} value={choice[d.id] ?? null}
                    onChange={(v) => {
                      setChoice((c) => (c[d.id] === v ? c : { ...c, [d.id]: v }));
                      setFileModes((m) => { if (!(d.id in m)) return m; const n = { ...m }; delete n[d.id]; return n; });
                      setSecrets((s) => ({ ...s, [d.id]: {} }));
                      setLoginAfter((l) => { const n = { ...l }; delete n[d.id]; return n; });
                    }} />
                  {choice[d.id] && (
                    <FileNeeds projectId={projectId} versionId={choice[d.id]} secrets={secrets[d.id] ?? {}}
                      onSecrets={(v) => setSecrets((s) => ({ ...s, [d.id]: v }))}
                      onMode={(m) => setFileModes((f) => (f[d.id] === m ? f : { ...f, [d.id]: m }))}
                      loginAfter={loginAfter[d.id] ?? null}
                      onLoginAfter={(v) => setLoginAfter((l) => {
                        const n = { ...l };
                        if (v) n[d.id] = v; else delete n[d.id];
                        return n;
                      })} />
                  )}
                </>)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      </Table.ScrollContainer>
      <Group mb="md" wrap="wrap">
        <Switch label="Dry run (read-only, no approval needed)" checked={dryRun} onChange={(e) => setDryRun(e.currentTarget.checked)} />
        <Group gap="xs"><Text size="sm">Apply mode</Text>
          <SegmentedControl size="xs" aria-label="How the file is applied" value={effectiveMode} onChange={setMode} disabled={!!forced}
            data={[{ value: 'merge', label: 'Additions' }, { value: 'replace', label: 'Complete file' }]} />
          {forced && <Text size="xs" c="dimmed">set by the chosen file</Text>}</Group>
      </Group>
      {required.length > 1 && (
        <Alert color="red" icon={<IconInfoCircle size={16} />} mb="md">
          The chosen files need different modes (a complete file and a script). Make one plan per kind of file.
        </Alert>
      )}
      {effectiveMode === 'replace' && (
        <Alert color="yellow" icon={<IconInfoCircle size={16} />} mb="md">
          Replace makes the running configuration equal to the chosen one, removing everything else. For a FortiGate full backup or a
          complete 2930F file, the device fetches the file over TFTP and restarts. Drivers that cannot replace are rejected at validation.
        </Alert>
      )}
      <Button disabled={sel.length === 0 || required.length > 1} loading={create.isPending}
        onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(`/deployments/${d.id}`) })}>
        Validate and preview
      </Button>
    </Card>
  );
}

/** Base file, then site file, for one device, as one plan (D-071). */
function NewStagingPlan({ projectId }: { projectId: string }) {
  const devices = useProjectDevices(projectId);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const configs = useConfigs(deviceId ?? '');
  const [base, setBase] = useState<string | null>(null);
  const [site, setSite] = useState<string | null>(null);
  const [loginAfter, setLoginAfter] = useState<string | null>(null);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [firstLogin, setFirstLogin] = useState(false);
  const navigate = useNavigate();
  const versions = configs.data ?? [];
  const options = (mode: string) => {
    const fitting = versions.filter((v) => !v.inspection?.apply_mode || v.inspection.apply_mode === mode);
    return (fitting.length ? fitting : versions).map((v) => ({ value: v.id, label: versionLabel(v) }));
  };
  const create = useAction(() => api.createStaging(projectId, {
    device_id: deviceId!, base_version_id: base!, site_version_id: site!,
    credential_after_ref_id: loginAfter,
    secrets: Object.keys(secrets).length ? secrets : undefined,
    first_login: firstLogin,
  }), (p) => `Staging plan created: step 1 ${stateLabel(p.steps[0]?.state ?? '').toLowerCase()}`);
  const ignoreMode = useCallback(() => undefined, []);

  return (
    <Card withBorder>
      <Title order={2} size="h4" mb="xs">New staging plan (base file, then site file)</Title>
      <Text size="sm" c="dimmed" mb="md">
        For a FortiGate staged with two files: step 1 restores the base file (replace, the device restarts), step 2 loads the
        site file (merge) once step 1 has succeeded. The site file therefore always lands on a clean base, never on an earlier
        site configuration. One approval covers both steps.
      </Text>
      <Stack gap="xs" maw={560}>
        <Select label="Device" placeholder="Choose a device" data={(devices.data ?? []).map((d) => ({ value: d.id, label: `${d.name} (${d.model})` }))}
          value={deviceId} onChange={(v) => { setDeviceId(v); setBase(null); setSite(null); setLoginAfter(null); setSecrets({}); }} />
        {deviceId && <>
          <Checkbox label="New unit: start with the first login" checked={firstLogin}
            onChange={(e) => setFirstLogin(e.currentTarget.checked)}
            description="The unit still has its factory login (admin, no password). Step 1 sets the device's login when the unit asks for a new password; the base file follows." />
          <Select label="Step 1 · base file" placeholder="Choose the base file" data={options('replace')}
            value={base} onChange={(v) => { setBase(v); setLoginAfter(null); }} />
          {base && <FileNeeds projectId={projectId} versionId={base} secrets={{}} onSecrets={() => undefined}
            onMode={ignoreMode} loginAfter={loginAfter} onLoginAfter={setLoginAfter} />}
          <Select label="Step 2 · site file" placeholder="Choose the site file" data={options('merge')}
            value={site} onChange={(v) => { setSite(v); setSecrets({}); }} />
          {site && <FileNeeds projectId={projectId} versionId={site} secrets={secrets} onSecrets={setSecrets}
            onMode={ignoreMode} loginAfter={null} onLoginAfter={() => undefined} />}
        </>}
        <Group>
          <Button disabled={!deviceId || !base || !site || base === site} loading={create.isPending}
            onClick={() => create.mutate(undefined, { onSuccess: (p) => void navigate(`/staging/${p.staging_id}`) })}>
            Create staging plan
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

/** A new unit's first login, as an approved plan (D-073): before a firmware plan. */
function NewFirstLogin({ projectId }: { projectId: string }) {
  const devices = useProjectDevices(projectId);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const navigate = useNavigate();
  const create = useAction(() => api.createFirstLogin(projectId, deviceId!),
    (d) => `First login planned: ${stateLabel(d.state).toLowerCase()}`);
  return (
    <Card withBorder>
      <Title order={2} size="h4" mb="xs">First login on a new unit</Title>
      <Text size="sm" c="dimmed" mb="md">
        A new FortiGate lets admin in without a password and then asks for a new one. UNDM checks this without answering
        (preview); once approved it sets the device&apos;s login (the approved password stored with the device) and logs in with it.
        Do this before the firmware plan. The staging plan can include it as its first step.
      </Text>
      <Group align="flex-end">
        <Select label="Device" placeholder="Choose a device" w="100%" maw={320}
          data={(devices.data ?? []).map((d) => ({ value: d.id, label: `${d.name} (${d.model})` }))}
          value={deviceId} onChange={setDeviceId} />
        <Button disabled={!deviceId} loading={create.isPending}
          onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(`/deployments/${d.id}`) })}>
          Check and plan the first login
        </Button>
      </Group>
    </Card>
  );
}

export function DeploymentsPage() {
  const [askToDelete, deleteDialog, canDelete] = usePlanDelete();
  const [params, setParams] = useSearchParams();
  const projects = useProjects();
  const all = useAllDeployments();
  const projectId = params.get('project');
  const preselected = (params.get('devices') ?? '').split(',').filter(Boolean);
  const version = params.get('version');
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));

  return (
    <>
      <PageHeader title="Plans" description="A plan is one approved piece of work on devices: load a file, upgrade firmware or set the first login. Make one, approve it, then run it." />
      <Stack>
        <Card withBorder>
          <Select label="System for a new plan" placeholder="Choose a system" maw={420}
            data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
            value={projectId} onChange={(v) => setParams(v ? { project: v } : {})} />
        </Card>
        {projectId && <NewPlan key={projectId + preselected.join() + (version ?? '')} projectId={projectId}
          preselected={preselected} version={version} />}
        {projectId && <NewFirstLogin key={`first-${projectId}`} projectId={projectId} />}
        {projectId && <NewStagingPlan key={`staging-${projectId}`} projectId={projectId} />}
        <Card withBorder padding={0}>
          {deleteDialog}
          <Title order={2} size="h5" p="md" pb={0}>All plans</Title>
          <QueryState isLoading={all.isLoading} error={all.error} />
          <Table.ScrollContainer minWidth={640}>
            <Table verticalSpacing="xs" horizontalSpacing="md" highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>System</Table.Th><Table.Th>Type</Table.Th><Table.Th>Created by</Table.Th><Table.Th>Approved by</Table.Th><Table.Th>Status</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(all.data ?? []).map((d) => (
                  <Table.Tr key={d.id}>
                    <Table.Td><Anchor component={Link} to={`/deployments/${d.id}`} size="sm">{fmtDate(d.created_at)}</Anchor></Table.Td>
                    <Table.Td>{names.get(d.project_id) ?? '—'}</Table.Td>
                    <Table.Td>{planKind(d)}
                      {d.staging_id && <> · <Anchor component={Link} to={`/staging/${d.staging_id}`} size="sm">staging step {d.staging_step}</Anchor></>}</Table.Td>
                    <Table.Td>{d.created_by}</Table.Td><Table.Td>{d.approved_by ?? '—'}</Table.Td>
                    <Table.Td><PlanStatus d={d} /></Table.Td>
                    <Table.Td>{canDelete(d) && <Tooltip label="Delete plan"><ActionIcon variant="subtle" color="red" aria-label={`Delete plan of ${fmtDate(d.created_at)}`}
                      onClick={() => askToDelete(d)}><IconTrash size={16} /></ActionIcon></Tooltip>}</Table.Td>
                  </Table.Tr>
                ))}
                {all.data?.length === 0 && <Table.Tr><Table.Td colSpan={7}><Text c="dimmed" ta="center" p="md">No plans yet.</Text></Table.Td></Table.Tr>}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      </Stack>
    </>
  );
}

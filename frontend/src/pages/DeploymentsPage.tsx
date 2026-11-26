import { Accordion, ActionIcon, Anchor, Button, Card, Checkbox, Group, SegmentedControl, Select, Stack, Switch, Table, Text, Title } from '@mantine/core';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../components/Badges';
import { Hint } from '../components/Hint';
import { Notice } from '../components/Notice';
import { PageHeader, QueryState } from '../components/Page';
import { PlanStatus } from '../features/plans/AttentionBadge';
import { usePlanDelete } from '../hooks/usePlanDelete';
import { fmtDate, planKind } from '../services/format';
import { RUNNING_STATES, useAction, useAllDeployments, useConfig, useConfigs, useCredentialRefs, useProjectDevices, useProjects } from '../hooks/queries';
import type { ConfigVersion, DeploymentSummary } from '../types/api';
import { ActionsHeader, DataTable } from '../components/DataTable';

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
import { paths } from '../paths';

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
        <Notice kind="error" mb="md">
          The chosen files need different modes (a complete file and a script). Make one plan per kind of file.
        </Notice>
      )}
      {effectiveMode === 'replace' && (
        <Hint mb="md" more="For a FortiGate full backup or a complete 2930F or Black Box file, the device fetches the file from this PC and restarts. Devices that cannot load a complete file are refused when the plan is checked.">
          A complete file makes the device's configuration equal to it: everything else is removed.
        </Hint>
      )}
      <Button disabled={sel.length === 0 || required.length > 1} loading={create.isPending}
        onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(paths.plan(d.id)) })}>
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
            onClick={() => create.mutate(undefined, { onSuccess: (p) => void navigate(paths.staging(p.staging_id)) })}>
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
          onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(paths.plan(d.id)) })}>
          Check and plan the first login
        </Button>
      </Group>
    </Card>
  );
}

/** The state groups of the plans list (D-122): what the person wants to find. */
const GROUPS: Record<string, (d: DeploymentSummary) => boolean> = {
  all: () => true,
  waiting: (d) => ['draft', 'awaiting_approval', 'ready'].includes(d.state),
  running: (d) => RUNNING_STATES.has(d.state),
  attention: (d) => d.state === 'recovery_required' && d.needs_attention !== false,
  finished: (d) => ['succeeded', 'failed', 'rolled_back', 'cancelled'].includes(d.state)
    || (d.state === 'recovery_required' && d.needs_attention === false),
};

/** Advanced → Plans: every plan of every system, filtered (D-122). New plans are made under
 *  "New plan"; Stage a system makes its own. */
export function PlansPage() {
  const [askToDelete, deleteDialog, canDelete] = usePlanDelete();
  const [params, setParams] = useSearchParams();
  const projects = useProjects();
  const all = useAllDeployments();
  const system = params.get('system');
  const group = params.get('show') ?? 'all';
  const kind = params.get('type');
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const kinds = [...new Set((all.data ?? []).map((d) => planKind({ ...d, dry_run: false })))].sort();
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v && !(k === 'show' && v === 'all')) next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  };
  const shown = (all.data ?? []).filter((d) => (!system || d.project_id === system)
    && (GROUPS[group] ?? GROUPS.all)(d) && (!kind || planKind({ ...d, dry_run: false }) === kind));
  return (
    <>
      <PageHeader title="Plans" description="Every plan of every system. A plan is one approved piece of work on devices; Stage a system makes them for you."
        primary={<Button component={Link} to={paths.planNew(system ? { system } : {})} leftSection={<IconPlus size={16} />}>New plan</Button>} />
      <Card mb="md">
        <Group align="flex-end" wrap="wrap">
          <Select label="System" placeholder="All systems" clearable w={260} value={system}
            data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))} onChange={(v) => set('system', v)} />
          <Select label="Type" placeholder="All types" clearable w={260} value={kind} data={kinds} onChange={(v) => set('type', v)} />
          <SegmentedControl aria-label="Show" value={group} onChange={(v) => set('show', v)}
            data={[{ value: 'all', label: 'All' }, { value: 'waiting', label: 'Waiting' }, { value: 'running', label: 'Running' },
              { value: 'attention', label: 'Needs attention' }, { value: 'finished', label: 'Finished' }]} />
        </Group>
      </Card>
      {deleteDialog}
      <Card padding={0}>
        <DataTable label="Plans" loading={all.isLoading} error={all.error} rowCount={shown.length} minWidth={720}
          empty={all.data?.length ? 'No plan matches these filters.' : 'No plans yet. Stage a system to make them.'}>
          <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>System</Table.Th><Table.Th>Type</Table.Th><Table.Th>Made by</Table.Th><Table.Th>Approved by</Table.Th><Table.Th>Status</Table.Th><ActionsHeader /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {shown.map((d) => (
              <Table.Tr key={d.id}>
                <Table.Td><Anchor component={Link} to={paths.plan(d.id)} size="sm">{fmtDate(d.created_at)}</Anchor></Table.Td>
                <Table.Td>{names.get(d.project_id) ?? '—'}</Table.Td>
                <Table.Td>{planKind(d)}
                  {d.staging_id && <> · <Anchor component={Link} to={paths.staging(d.staging_id)} size="sm">staging plan, step {d.staging_step}</Anchor></>}</Table.Td>
                <Table.Td>{d.created_by}</Table.Td><Table.Td>{d.approved_by ?? '—'}</Table.Td>
                <Table.Td><PlanStatus d={d} /></Table.Td>
                <Table.Td>{canDelete(d) && <ActionIcon variant="subtle" color="red" aria-label={`Delete plan of ${fmtDate(d.created_at)}`}
                  onClick={() => askToDelete(d)}><IconTrash size={16} /></ActionIcon>}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </DataTable>
      </Card>
    </>
  );
}

/** Advanced → Plans → New plan (D-122): a configuration file for chosen devices; the plan
 *  types outside Stage a system are folded away. */
export function PlanNewPage() {
  const [params, setParams] = useSearchParams();
  const projects = useProjects();
  // `project` is the parameter's name before D-120.
  const projectId = params.get('system') ?? params.get('project');
  const preselected = (params.get('devices') ?? '').split(',').filter(Boolean);
  const version = params.get('version');
  return (
    <>
      <PageHeader title="New plan" breadcrumbs={[{ label: 'Plans', to: paths.plans }]}
        description="For engineers. Stage a system makes the plans for a new system by itself; here you make one for chosen devices." />
      <Stack>
        <Card>
          <Select label="System" placeholder="Choose a system" maw={420}
            data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
            value={projectId} onChange={(v) => setParams(v ? { system: v } : {})} />
          <Text size="xs" c="dimmed" mt={6}>A firmware upgrade is planned on the{' '}
            <Anchor component={Link} to={paths.firmware()} size="xs">Firmware page</Anchor>.</Text>
        </Card>
        {projectId && <NewPlan key={projectId + preselected.join() + (version ?? '')} projectId={projectId}
          preselected={preselected} version={version} />}
        {projectId && (
          <Accordion variant="separated">
            <Accordion.Item value="more">
              <Accordion.Control>More plan types (FortiGate, outside Stage a system)</Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  <NewFirstLogin key={`first-${projectId}`} projectId={projectId} />
                  <NewStagingPlan key={`staging-${projectId}`} projectId={projectId} />
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        )}
      </Stack>
    </>
  );
}

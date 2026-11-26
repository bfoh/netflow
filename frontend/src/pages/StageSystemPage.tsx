import { Anchor, Badge, Button, Card, Group, SegmentedControl, Select, SimpleGrid, Stack, Stepper, Text, TextInput, Title } from '@mantine/core';
import { IconCheck, IconPlus } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';

import { EnvironmentBadge } from '../components/Badges';
import { DialogError } from '../components/ConfirmDialog';
import { PageHeader, QueryState } from '../components/Page';
import { BenchStep } from '../features/stage/BenchStep';
import { type Choice, type Choices, EMPTY_CHOICE, loadChoices, planSteps, saveChoices } from '../features/stage/choices';
import { FilesStep } from '../features/stage/FilesStep';
import { ZoneField } from '../features/stage/GeneratePanel';
import { ReportStep } from '../features/stage/ReportStep';
import { assignRoles, roleDefaults, ROLES, type Role, type RoleKey } from '../features/stage/roles';
import { RunStep } from '../features/stage/RunStep';
import {
  useAction, useCredentialRefs, useDeviceModels, useLoginDefaults, useProject, useProjectDevices, useProjects, useProjectStagings,
} from '../hooks/queries';
import { api } from '../services/api';
import { fmtDate } from '../services/format';
import type { Device } from '../types/api';
import { Hint } from '../components/Hint';

const STEPS = ['System and devices', 'Files and firmware', 'Bench check', 'Run', 'Report'];

/** Step 0 without a system: choose one or make a new one. */
function ChooseSystem() {
  const projects = useProjects();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const create = useAction(() => api.createProject({ name: name.trim(), purpose: 'Staging' }), 'System created', { errorInDialog: true });
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }}>
      <Card withBorder>
        <Title order={2} size="h5" mb="xs">A new system</Title>
        <Stack gap="xs">
          <TextInput label="System name" placeholder="e.g. site 12 staging" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <DialogError error={create.error} />
          <Group><Button leftSection={<IconPlus size={16} />} disabled={!name.trim()} loading={create.isPending}
            onClick={() => create.mutate(undefined, { onSuccess: (p) => void navigate(`/stage/${p.id}`) })}>Create and continue</Button></Group>
        </Stack>
      </Card>
      <Card withBorder>
        <Title order={2} size="h5" mb="xs">A system you have</Title>
        <Select label="System" placeholder={projects.data?.length ? 'Choose a system' : 'No systems yet'} searchable
          data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
          onChange={(v) => { if (v) void navigate(`/stage/${v}`); }} />
      </Card>
    </SimpleGrid>
  );
}

/** Which login a device of each role uses at the start of its plan. */
const LOGIN_HINT: Record<RoleKey, string> = {
  firewall: 'The approved login. On a new unit, the first login step sets it.',
  blackbox: 'New unit: admin with no password. In step 2 choose the approved login as "Login after loading".',
  aruba_a: 'The approved login. Preconfigured switch: the console setup erases it first with its current login (add that login too).',
  aruba_b: 'The approved login. Preconfigured switch: the console setup erases it first with its current login (add that login too).',
  modem: 'The approved login, user name admin: its first access gives the modem this password. The modem refuses a password it finds too simple.',
};

/** One role: its device, or a button that adds it with the bench defaults. */
function RoleCard({ role, device, projectId, systemName, simulated }: {
  role: Role; device?: Device; projectId: string; systemName: string; simulated: boolean;
}) {
  const models = useDeviceModels();
  const refs = useCredentialRefs(projectId);
  const defaults = useLoginDefaults();
  const real = !simulated;
  const model = models.data?.find((m) => m.model_id === role.modelId);
  const slug = systemName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'system';
  const add = useAction(() => api.createDevice(projectId, {
    name: `${slug}-${role.nameSuffix}`, manufacturer: model?.manufacturer ?? '', product_family: model?.product_family ?? '',
    model: role.model, category: model?.category ?? 'switch', os_family: model?.os_family ?? '',
    driver_id: simulated ? role.simulatedDriver : role.realDriver, environment: simulated ? 'simulated' : 'lab',
    ...(role.address ? { management_address: role.address, management_protocol: 'ssh' as const } : {}), role: role.title,
    // Its login from Settings → For all systems (D-105); simulated devices need none.
    ...(real && roleDefaults(role, defaults.data).login ? { credential_ref_id: roleDefaults(role, defaults.data).login } : {}),
  }), `${role.title} added`, { errorInDialog: true });
  const setLogin = useAction((ref: string | null) => api.updateDevice(device!.id, { credential_ref_id: ref }), 'Login chosen');
  return (
    <Card withBorder>
      <Group justify="space-between" wrap="nowrap" mb={4}>
        <Title order={2} size="h5">{role.title}</Title>
        {device && <EnvironmentBadge env={device.environment} />}
      </Group>
      <Text size="xs" c="dimmed" mb="xs">{role.hint}</Text>
      {device ? (
        <Stack gap={6}>
          <Group gap="xs"><Anchor component={Link} to={`/devices/${device.id}`} fw={600} size="sm">{device.name}</Anchor>
            <Text size="sm" ff="monospace" c="dimmed">{device.management_address || (role.consoleCable ? `console cable${device.console_port ? ` · ${device.console_port}` : ' only'}` : '')}</Text></Group>
          <Select size="xs" label="Its login" clearable w="100%" maw={320}
            description={LOGIN_HINT[role.key]}
            placeholder={refs.data?.length ? 'Choose a login' : 'Add logins on the system page first'}
            data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))}
            value={device.credential_ref_id} onChange={(v) => setLogin.mutate(v)} />
        </Stack>
      ) : (
        <Stack gap={6}>
          <Text size="sm">Not in this system yet.</Text>
          <DialogError error={add.error} />
          <Group><Button size="xs" leftSection={<IconPlus size={14} />} loading={add.isPending} disabled={!model}
            onClick={() => add.mutate(undefined)}>Add it ({role.address || 'console cable only'})</Button></Group>
        </Stack>
      )}
    </Card>
  );
}

/** Gives the devices without a login their default login (Settings → For all systems). */
function DefaultLoginsBar({ roles }: { roles: { role: Role; device: Device }[] }) {
  const defaults = useLoginDefaults();
  const todo = roles.filter(({ role, device }) => device.environment !== 'simulated' && !device.credential_ref_id
    && roleDefaults(role, defaults.data).login);
  const apply = useAction(async () => {
    for (const { role, device } of todo) {
      await api.updateDevice(device.id, { credential_ref_id: roleDefaults(role, defaults.data).login });
    }
  }, 'Default logins chosen');
  const anyDefault = !!defaults.data?.firewall && Object.values(defaults.data).some((k) => Object.values(k).some(Boolean));
  if (!anyDefault) {
    return (
      <Hint>Logins are set once for all systems in <Anchor component={Link} to="/settings?tab=shared" size="xs">Settings → For all systems</Anchor>,
        with a default login per device; new devices then start with theirs.</Hint>
    );
  }
  return (
    <Group gap="sm">
      {todo.length > 0 && <Button size="xs" variant="light" loading={apply.isPending} onClick={() => apply.mutate(undefined)}>
        Use the default logins ({todo.length} {todo.length === 1 ? 'device' : 'devices'})</Button>}
      <Text size="xs" c="dimmed">Default logins come from <Anchor component={Link} to="/settings?tab=shared" size="xs">Settings → For all systems</Anchor>;
        a device that differs can have another one here.</Text>
    </Group>
  );
}

export function StageSystemPage() {
  const { projectId = '' } = useParams();
  // A new system starts with its own choices: the page is made afresh per system.
  return <StageSystem key={projectId} projectId={projectId} />;
}

function StageSystem({ projectId }: { projectId: string }) {
  const [params, setParams] = useSearchParams();
  const active = Math.min(Number(params.get('step') ?? 0) || 0, STEPS.length - 1);
  const setActive = (n: number) => setParams({ step: String(n) });
  const project = useProject(projectId);
  const devices = useProjectDevices(projectId);
  const stagings = useProjectStagings(projectId, active === 3 || active === 4);
  const [simulated, setSimulated] = useState('real');
  const [choices, setChoices] = useState<Choices>(() => (projectId ? loadChoices(projectId) : {}));
  const assigned = useMemo(() => assignRoles(devices.data ?? []), [devices.data]);
  const roles = ROLES.flatMap((role) => (assigned[role.key] ? [{ role, device: assigned[role.key]! }] : []));
  const setChoice = (key: string, c: Choice) => {
    const next = { ...choices, [key]: c };
    setChoices(next);
    saveChoices(projectId, next);
  };
  const filesReady = roles.length > 0 && roles.every(({ role, device }) => planSteps(role, choices[role.key as RoleKey] ?? EMPTY_CHOICE, device).missing.length === 0);

  if (!projectId) {
    return (
      <>
        <PageHeader title="Stage a system" description="Take the devices of one system from factory default to their approved firmware and files, step by step." />
        <ChooseSystem />
      </>
    );
  }
  if (!project.data) return <QueryState isLoading={project.isLoading} error={project.error} />;
  return (
    <>
      <PageHeader title={`Stage a system · ${project.data.name}`}
        description="Step by step: the devices, their files and firmware, the bench, then one plan per device. Nothing changes a device until you approve and run its plan."
        actions={<Button variant="default" component={Link} to={`/projects/${projectId}`}>System page</Button>} />
      {/* A finished system shows every step done (D-108); the content still follows `active`. */}
      <Stepper active={project.data.staged_at ? STEPS.length : active} onStepClick={setActive} size="sm" mb="lg" allowNextStepsSelect>
        {STEPS.map((label, i) => (
          <Stepper.Step key={label} label={label}
            completedIcon={<IconCheck size={16} />}
            description={i === 0 ? `${roles.length} of ${ROLES.length} devices` : i === 1 ? (filesReady ? 'ready' : 'to choose')
              : i === STEPS.length - 1 && project.data!.staged_at ? `finished ${fmtDate(project.data!.staged_at)}` : undefined} />
        ))}
      </Stepper>
      {active === 0 && (
        <Stack>
          <Group justify="space-between" wrap="wrap">
            <Text size="sm" c="dimmed">Devices are found by model; add the missing ones with the bench defaults (you can edit them later).</Text>
            <SegmentedControl size="xs" aria-label="Devices to add" value={simulated} onChange={setSimulated}
              data={[{ value: 'real', label: 'Real devices on the bench' }, { value: 'simulated', label: 'Practice (simulated)' }]} />
          </Group>
          <ZoneField key={`${project.data.id}-${project.data.zone ?? ''}`} project={project.data} />
          {(devices.data ?? []).length > roles.length && (
            <Hint>This system also has devices that play no staging role; they are left out here.</Hint>
          )}
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            {ROLES.map((role) => (
              <RoleCard key={role.key} role={role} device={assigned[role.key]} projectId={projectId}
                systemName={project.data!.name} simulated={simulated === 'simulated'} />
            ))}
          </SimpleGrid>
          <DefaultLoginsBar roles={roles} />
        </Stack>
      )}
      {active === 1 && <FilesStep project={project.data} roles={roles} choices={choices} onChange={setChoice}
        onReplace={(next) => { setChoices(next); saveChoices(projectId, next); }} />}
      {active === 2 && <BenchStep roles={roles} />}
      {active === 3 && <RunStep projectId={projectId} roles={roles} choices={choices} stagings={stagings.data ?? []} />}
      {active === 4 && <ReportStep project={project.data} roles={roles} stagings={stagings.data ?? []} />}
      <Group justify="space-between" mt="lg" className="no-print">
        <Button variant="default" disabled={active === 0} onClick={() => setActive(active - 1)}>Back</Button>
        {active < STEPS.length - 1 && <Button onClick={() => setActive(active + 1)}>Next: {STEPS[active + 1]}</Button>}
      </Group>
      {active === 0 && roles.length === 0 && <Badge mt="xs" color="gray" variant="light" tt="none">Add at least one device to continue usefully</Badge>}
    </>
  );
}

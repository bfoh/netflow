import { Anchor, Badge, Button, Card, Group, Menu, SegmentedControl, Select, SimpleGrid, Stack, Stepper, Text, TextInput, Title } from '@mantine/core';
import { IconArrowLeft, IconCheck, IconPlus } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router';

import { DialogError } from '../components/ConfirmDialog';
import { LoadingLines, PageHeader, QueryState } from '../components/Page';
import { ConsoleSetup } from '../features/provisioning/ConsoleSetup';
import { BenchStep } from '../features/stage/BenchStep';
import { type Choice, type Choices, EMPTY_CHOICE, loadChoices, planSteps, saveChoices } from '../features/stage/choices';
import { FilesStep } from '../features/stage/FilesStep';
import { ZoneField } from '../features/stage/GeneratePanel';
import { ReportStep } from '../features/stage/ReportStep';
import { RoleCard } from '../features/stage/RoleCard';
import { assignRoles, deviceInputFor, roleDefaults, ROLES, type Role, type RoleKey } from '../features/stage/roles';
import { RunStep } from '../features/stage/RunStep';
import { lastSystem, placeOf, rememberPlace, type WizardMode } from '../features/stage/wizardMemory';
import {
  useAction, useDeviceModels, useLoginDefaults, useProject, useProjectDevices, useProjects, useProjectStagings,
} from '../hooks/queries';
import { api } from '../services/api';
import { fmtDate } from '../services/format';
import type { Device } from '../types/api';
import { Hint } from '../components/Hint';
import { Notice } from '../components/Notice';
import { paths } from '../paths';

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
            onClick={() => create.mutate(undefined, { onSuccess: (p) => void navigate(paths.stage(p.id)) })}>Create and continue</Button></Group>
        </Stack>
      </Card>
      <Card withBorder>
        <Title order={2} size="h5" mb="xs">A system you have</Title>
        <Select label="System" placeholder={projects.data?.length ? 'Choose a system' : 'No systems yet'} searchable
          data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
          onChange={(v) => { if (v) void navigate(paths.stage(v)); }} />
      </Card>
    </SimpleGrid>
  );
}

/** A device's console work inside the wizard, with the way back above and below it. */
function WizardConsole({ device, loading, back }: { device?: Device; loading: boolean; back: { label: string; onClick: () => void } }) {
  if (!device) return loading ? <LoadingLines lines={4} /> : <Notice kind="error" title="This device is not in the system">It may have been deleted.</Notice>;
  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>{device.name}: console</Title>
        <Button variant="default" leftSection={<IconArrowLeft size={16} />} onClick={back.onClick}>{back.label}</Button>
      </Group>
      <ConsoleSetup device={device} back={back} />
    </Stack>
  );
}

/** Adds every role that has no device yet, with the same defaults as each card's "Add it". */
function AddAllMissing({ projectId, systemName, simulated, missing }: {
  projectId: string; systemName: string; simulated: boolean; missing: Role[];
}) {
  const models = useDeviceModels();
  const defaults = useLoginDefaults();
  const addable = missing.filter((role) => models.data?.some((m) => m.model_id === role.modelId));
  const add = useAction(async () => {
    for (const role of addable) {
      const model = models.data?.find((m) => m.model_id === role.modelId);
      await api.createDevice(projectId, deviceInputFor(role, { systemName, model, simulated, defaults: defaults.data }));
    }
  }, `${addable.length} ${addable.length === 1 ? 'device' : 'devices'} added`, { errorInDialog: true });
  if (addable.length === 0) return null;
  return (
    <Stack gap={4} align="flex-end">
      <Button leftSection={<IconPlus size={16} />} loading={add.isPending} onClick={() => add.mutate(undefined)}>
        Add all missing devices ({addable.length})
      </Button>
      <DialogError error={add.error} />
    </Stack>
  );
}

/** Gives the devices without a login their default login (Settings → Logins). */
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
      <Hint>Logins are set once for all systems in <Anchor component={Link} to={paths.settings('logins')} size="xs">Settings → Logins</Anchor>,
        with a default login per device; new devices then start with theirs.</Hint>
    );
  }
  return (
    <Group gap="sm">
      {todo.length > 0 && <Button size="xs" variant="light" loading={apply.isPending} onClick={() => apply.mutate(undefined)}>
        Use the default logins ({todo.length} {todo.length === 1 ? 'device' : 'devices'})</Button>}
      <Text size="xs" c="dimmed">Default logins come from <Anchor component={Link} to={paths.settings('logins')} size="xs">Settings → Logins</Anchor>;
        a device that differs can have another one here.</Text>
    </Group>
  );
}

export function StageSystemPage() {
  const { projectId = '' } = useParams();
  if (!projectId) return <ResumeOrChoose />;
  // A new system starts with its own choices: the page is made afresh per system.
  return <StageSystem key={projectId} projectId={projectId} />;
}

/** "Stage a system" goes back to the system last worked on, at its step, while it is not
 *  finished (D-120); `?choose=1` always shows the chooser. */
function ResumeOrChoose() {
  const [params] = useSearchParams();
  const projects = useProjects();
  const last = params.get('choose') === '1' ? null : lastSystem();
  if (last) {
    if (projects.isLoading) return <LoadingLines lines={3} />;
    const p = projects.data?.find((x) => x.id === last);
    if (p && !p.staged_at) return <Navigate replace to={paths.stage(last, placeOf(last)?.step ?? 0)} />;
  }
  return (
    <>
      <PageHeader title="Stage a system" description="Take the devices of one system from factory default to their approved firmware and files, step by step." />
      <ChooseSystem />
    </>
  );
}

function StageSystem({ projectId }: { projectId: string }) {
  const [params, setParams] = useSearchParams();
  const active = Math.min(Number(params.get('step') ?? 0) || 0, STEPS.length - 1);
  const setActive = (n: number) => setParams({ step: String(n) });
  // Console setup inside the wizard (D-121): the stepper stays, "Back to <step>" and the
  // browser's Back both return to the step it was opened from.
  const consoleId = params.get('console');
  // Coming back from the console, the step shows what the console work just changed.
  const qc = useQueryClient();
  const project = useProject(projectId);
  const devices = useProjectDevices(projectId);
  const stagings = useProjectStagings(projectId, active === 3 || active === 4);
  const [simulated, setSimulated] = useState<WizardMode>(() => placeOf(projectId)?.mode ?? 'real');
  // Remember the step and the kind of devices, so Stage a system comes back here (D-120).
  useEffect(() => { rememberPlace(projectId, { step: active, mode: simulated }); }, [projectId, active, simulated]);
  const [choices, setChoices] = useState<Choices>(() => (projectId ? loadChoices(projectId) : {}));
  const assigned = useMemo(() => assignRoles(devices.data ?? []), [devices.data]);
  const roles = ROLES.flatMap((role) => (assigned[role.key] ? [{ role, device: assigned[role.key]! }] : []));
  const setChoice = (key: string, c: Choice) => {
    const next = { ...choices, [key]: c };
    setChoices(next);
    saveChoices(projectId, next);
  };
  const filesReady = roles.length > 0 && roles.every(({ role, device }) => planSteps(role, choices[role.key as RoleKey] ?? EMPTY_CHOICE, device).missing.length === 0);

  if (!project.data) return <QueryState isLoading={project.isLoading} error={project.error} />;
  return (
    <>
      <PageHeader title={`Stage a system · ${project.data.name}`}
        description="Step by step: the devices, their files and firmware, the bench, then one plan per device. Nothing changes a device until you approve and run its plan."
        secondary={<Button variant="default" component={Link} to={paths.system(projectId)}>System page</Button>}
        menu={<Menu.Item component={Link} to={paths.stageChooser}>Stage another system</Menu.Item>} />
      {/* A finished system shows every step done (D-108); the content still follows `active`. */}
      <Stepper active={project.data.staged_at ? STEPS.length : active} onStepClick={setActive} size="sm" mb="lg" allowNextStepsSelect>
        {STEPS.map((label, i) => (
          <Stepper.Step key={label} label={label}
            completedIcon={<IconCheck size={16} />}
            description={i === 0 ? `${roles.length} of ${ROLES.length} devices` : i === 1 ? (filesReady ? 'ready' : 'to choose')
              : i === STEPS.length - 1 && project.data!.staged_at ? `finished ${fmtDate(project.data!.staged_at)}` : undefined} />
        ))}
      </Stepper>
      {consoleId && (
        <WizardConsole device={(devices.data ?? []).find((d) => d.id === consoleId)} loading={devices.isLoading}
          back={{ label: `Back to ${STEPS[active]}`, onClick: () => { void qc.invalidateQueries(); setActive(active); } }} />
      )}
      {!consoleId && active === 0 && (
        <Stack>
          <Group justify="space-between" wrap="wrap" align="flex-end">
            <Stack gap={4}>
              <Text size="sm" c="dimmed">Devices are found by model; add the missing ones with the bench defaults (you can edit them later).</Text>
              <SegmentedControl size="xs" aria-label="Devices to add" value={simulated} w="fit-content"
                onChange={(v) => setSimulated(v === 'simulated' ? 'simulated' : 'real')}
                data={[{ value: 'real', label: 'Real devices on the bench' }, { value: 'simulated', label: 'Practice (simulated)' }]} />
            </Stack>
            <AddAllMissing projectId={projectId} systemName={project.data.name} simulated={simulated === 'simulated'}
              missing={ROLES.filter((role) => !assigned[role.key])} />
          </Group>
          <ZoneField key={project.data.id} project={project.data} />
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
      {!consoleId && active === 1 && <FilesStep project={project.data} roles={roles} choices={choices} onChange={setChoice}
        onReplace={(next) => { setChoices(next); saveChoices(projectId, next); }} />}
      {!consoleId && active === 2 && <BenchStep roles={roles} />}
      {!consoleId && active === 3 && <RunStep projectId={projectId} roles={roles} choices={choices} stagings={stagings.data ?? []} />}
      {!consoleId && active === 4 && <ReportStep project={project.data} roles={roles} stagings={stagings.data ?? []} />}
      {!consoleId && <Group justify="space-between" mt="lg" className="no-print">
        <Button variant="default" disabled={active === 0} onClick={() => setActive(active - 1)}>Back</Button>
        {active < STEPS.length - 1 && <Button onClick={() => setActive(active + 1)}>Next: {STEPS[active + 1]}</Button>}
      </Group>}
      {active === 0 && roles.length === 0 && <Badge mt="xs" color="gray" variant="light" tt="none">Add at least one device to continue usefully</Badge>}
    </>
  );
}

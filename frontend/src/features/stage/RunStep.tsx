import { Anchor, Badge, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconClock, IconTerminal2 } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import { StateBadge } from '../../components/Badges';
import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useStaging } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { Device, StagingIndex } from '../../types/api';
import { type Choice, EMPTY_CHOICE, planSteps, wantsFirstLogin } from './choices';
import { addressTakenBy, canMoveAside, SPARE_ADDRESS, temporaryAddress, type Role, STEP_TIME, STEP_WORDS, type StepKind } from './roles';
import { StagingControls } from './StagingControls';
import { stagingStatus } from './staging';
import { EmptyState } from '../../components/EmptyState';
import { Notice } from '../../components/Notice';

const CONSOLE_DONE = new Set(['bootstrapped', 'managed']);

/** The step kinds a plan will have, in words, with the console setup in front for the Aruba. */
function stepKinds(role: Role, c: Choice, device: Device): StepKind[] {
  return role.steps.filter((k) => (k === 'first_login' ? wantsFirstLogin(c, device) : k === 'firmware' ? !!c.imageId : true));
}

function PlannedSteps({ role, choice, device }: { role: Role; choice: Choice; device: Device }) {
  return (
    <Stack gap={4}>
      {stepKinds(role, choice, device).map((k, i) => (
        <Group key={k} justify="space-between" wrap="nowrap">
          <Text size="sm">{i + 1}. {STEP_WORDS[k]}</Text>
          {k === 'console'
            ? (CONSOLE_DONE.has(device.provisioning_status)
              ? <Badge color="teal" variant="light" tt="none">Done</Badge>
              : <Badge color="orange" variant="light" tt="none">To do first</Badge>)
            : <Text size="xs" c="dimmed"><IconClock size={11} /> {STEP_TIME[k]}</Text>}
        </Group>
      ))}
    </Stack>
  );
}

function LivePlan({ stagingId }: { stagingId: string }) {
  const [started, setStarted] = useState(false);
  const plan = useStaging(stagingId, started);
  const steps = plan.data?.steps ?? [];
  const s = stagingStatus(steps);
  const last = steps.flatMap((x) => x.events).at(-1);
  return (
    <Stack gap="xs">
      {steps.map((step) => (
        <Group key={step.id} justify="space-between" wrap="nowrap">
          <Anchor component={Link} to={`/deployments/${step.id}`} size="sm">
            {step.staging_step}. {step.kind === 'first_login' ? 'First login' : step.kind === 'free_address' ? 'Make room (move the other switch aside)' : step.kind === 'firmware' ? 'Firmware'
              : step.apply_mode === 'replace' ? 'Complete file' : 'Script'}
          </Anchor>
          <StateBadge state={step.state} />
        </Group>
      ))}
      {s.running && last && <Text size="xs" c="dimmed" lineClamp={2}>{fmtDate(last.timestamp)} · {last.message}</Text>}
      {s.ended && <Text size="xs" c="red">A step did not succeed; the later steps did not run. Open it for the reason.</Text>}
      <Group justify="space-between">
        <StagingControls stagingId={stagingId} steps={steps} size="xs" onStarted={() => setStarted(true)} />
        <Anchor component={Link} to={`/staging/${stagingId}`} size="xs">All events</Anchor>
      </Group>
    </Stack>
  );
}

function DeviceRun({ projectId, role, device, choice, latest, all }: {
  projectId: string; role: Role; device: Device; choice: Choice; latest?: StagingIndex; all: { device: Device }[];
}) {
  const [fresh, setFresh] = useState(false);
  // Its file moves it to an address another device of the system already has (both 2930F).
  const taken = choice.fileId ? addressTakenBy(role, device, all) : undefined;
  const { steps, missing } = planSteps(role, choice, device, taken);
  const parked = temporaryAddress(device);
  const consoleTodo = role.steps.includes('console') && !CONSOLE_DONE.has(device.provisioning_status);
  const make = useAction(() => api.createDeviceStaging(projectId, { device_id: device.id, steps }),
    (p) => `Plan made for ${device.name}: ${p.steps.length} steps waiting for approval`, { errorInDialog: true });
  const finished = latest && latest.states.every((x) => x === 'succeeded');
  const usable = latest && !fresh;
  const takenNotice = taken && !(finished && !fresh) && (canMoveAside(taken) ? (
    <Notice kind="status" compact>
      Its file moves it to {role.addressAfter}, where {taken.name} answers. Stage {taken.name} first. This plan then
      moves {taken.name} to {SPARE_ADDRESS} until its next power-on (nothing is saved on it): no cable to unplug.
    </Notice>
  ) : (
    <Notice kind="caution" compact>
      Its file moves it to {role.addressAfter}, where {taken.name} answers. Unplug {taken.name} from the small switch
      before you run this plan. If it still answers there, the file step stops before sending (nothing changed).
    </Notice>
  ));
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <div>
          <Title order={3} size="h5">{device.name}</Title>
          <Text size="xs" c="dimmed">{role.title} · {device.management_address}</Text>
        </div>
        {finished && !fresh && <Badge color="teal" variant="filled" tt="none">Staged</Badge>}
      </Group>
      {parked && <Notice kind="settled" compact mb="xs">Running at {parked} until its next power-on, to leave {device.management_address} free.
        Its saved configuration is unchanged.</Notice>}
      {usable ? (
        <Stack gap="xs">
          {takenNotice}
          <LivePlan stagingId={latest.staging_id} />
          <Button size="xs" variant="subtle" onClick={() => setFresh(true)}>Make a new plan for this device…</Button>
        </Stack>
      ) : (
        <Stack gap="xs">
          <PlannedSteps role={role} choice={choice} device={device} />
          {takenNotice}
          {consoleTodo && (
            <Notice kind="caution" compact action={<Button size="xs" variant="light" component={Link} to={`/provisioning?device=${device.id}`}
              leftSection={<IconTerminal2 size={14} />}>Open console setup</Button>}>
              Do its console setup first (new switch, or a preconfigured one: tick “erase first” there), so it answers at {device.management_address}.
            </Notice>
          )}
          {missing.length > 0 && <Text size="xs" c="orange"><IconAlertTriangle size={12} /> Still needed: {missing.join(', ')} (step 2).</Text>}
          <DialogError error={make.error} />
          <Group>
            <Button size="xs" disabled={steps.length === 0 || missing.length > 0 || consoleTodo} loading={make.isPending}
              onClick={() => make.mutate(undefined, { onSuccess: () => setFresh(false) })}>Make the plan</Button>
            {fresh && latest && <Button size="xs" variant="subtle" onClick={() => setFresh(false)}>Back to the last plan</Button>}
          </Group>
          <Text size="xs" c="dimmed">Making the plan checks the files and the image and changes nothing. Then approve it and run it.</Text>
        </Stack>
      )}
    </Card>
  );
}

/** Step 4: one card per device: make the plan, approve, run, follow. */
export function RunStep({ projectId, roles, choices, stagings }: {
  projectId: string; roles: { role: Role; device: Device }[]; choices: Partial<Record<string, Choice>>; stagings: StagingIndex[];
}) {
  if (roles.length === 0) return <EmptyState>Add the devices first (step 1: System and devices).</EmptyState>;
  return (
    <Stack>
      <Text size="sm" c="dimmed">Devices run independently: start one while another restarts. The runs continue on the server if you
        leave this page. Order inside each device: as listed. Two devices that end at the same address (the two 2930F) run one
        after the other: the card says which to unplug first.</Text>
      <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }}>
        {roles.map(({ role, device }) => (
          <DeviceRun key={role.key} projectId={projectId} role={role} device={device}
            choice={choices[role.key] ?? EMPTY_CHOICE}
            latest={stagings.find((x) => x.device_id === device.id)} all={roles} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}

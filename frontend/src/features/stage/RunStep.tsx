import { ActionIcon, Anchor, Button, Card, Group, Menu, Modal, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconCheck, IconClock, IconDots, IconPlayerPlay, IconTerminal2 } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router';

import { StateBadge, Tag } from '../../components/Badges';
import { InlineStatus } from '../../components/InlineStatus';
import { LoadingLines } from '../../components/Page';
import { ReasonButton } from '../../components/ReasonButton';
import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useStaging } from '../../hooks/queries';
import { api } from '../../services/api';
import { stepName } from '../../services/labels';
import { fmtDate } from '../../services/format';
import type { Device, StagingIndex, StagingPlan } from '../../types/api';
import { type Choice, EMPTY_CHOICE, planSteps, wantsFirstLogin } from './choices';
import { GuidedRun } from './GuidedRun';
import { addressTakenBy, canMoveAside, CONSOLE_DONE, portOff, type Role, STEP_TIME, STEP_WORDS, type StepKind } from './roles';
import { ApproveRunBody } from './ApproveRun';
import { StagingControls } from './StagingControls';
import { failureReason, stagingStatus } from './staging';
import { StartAllDialog } from './StartAllDialog';
import { startOrder } from './startOrder';
import { EmptyState } from '../../components/EmptyState';
import { Notice } from '../../components/Notice';
import { paths } from '../../paths';


/** The step kinds a plan will have, in words, with the console setup in front for the Aruba. */
function stepKinds(role: Role, c: Choice, device: Device): StepKind[] {
  return role.steps.filter((k) => (k === 'first_login' ? wantsFirstLogin(c, device) : k === 'firmware' ? !!c.imageId : true));
}

function PlannedSteps({ role, choice, device }: { role: Role; choice: Choice; device: Device }) {
  return (
    <Stack gap={4}>
      {stepKinds(role, choice, device).map((k, i) => (
        <Group key={k} justify="space-between" wrap="nowrap">
          <Text size="sm">{i + 1}. {k === 'console' && role.consoleWords ? role.consoleWords
            : k === 'file' && role.consoleCable ? 'Its configuration file (console)' : STEP_WORDS[k]}</Text>
          {k === 'console'
            ? (CONSOLE_DONE.has(device.provisioning_status)
              ? <Tag tone="success">Done</Tag>
              : <Tag tone="warning">To do first</Tag>)
            : <Text size="xs" c="dimmed"><IconClock size={11} /> {STEP_TIME[k]}</Text>}
        </Group>
      ))}
    </Stack>
  );
}

function LivePlan({ stagingId, onRetry }: { stagingId: string; onRetry: () => void }) {
  const [started, setStarted] = useState(false);
  const plan = useStaging(stagingId, started);
  const steps = plan.data?.steps ?? [];
  const s = stagingStatus(steps);
  const last = steps.flatMap((x) => x.events).at(-1);
  const failed = s.ended ? failureReason(steps) : null;
  return (
    <Stack gap="xs">
      {steps.map((step) => (
        <Group key={step.id} justify="space-between" wrap="nowrap">
          <Anchor component={Link} to={paths.plan(step.id)} size="sm">
            {step.staging_step}. {stepName(step.kind, step.apply_mode)}
          </Anchor>
          <StateBadge state={step.state} />
        </Group>
      ))}
      {s.running && last && <Text size="xs" c="dimmed" lineClamp={2} role="status">{fmtDate(last.timestamp)} · {last.message}</Text>}
      {failed && (
        <Notice kind={failed.step.state === 'recovery_required' ? 'error' : 'settled'} compact
          title={failed.step.state === 'recovery_required' ? 'Needs attention: check the device' : 'It did not finish; the later steps did not run'}
          action={<Group gap="xs">
            <Button size="xs" variant="default" component={Link} to={paths.plan(failed.step.id)}>
              {failed.step.state === 'recovery_required' ? 'Open the step to mark it checked' : 'Open the step'}</Button>
            <Button size="xs" onClick={onRetry}>Try again…</Button>
          </Group>}>
          {failed.text}
        </Notice>
      )}
      <Group justify="space-between" align="flex-start">
        <StagingControls stagingId={stagingId} steps={steps} size="xs" combined onStarted={() => setStarted(true)} />
        <Anchor component={Link} to={paths.staging(stagingId)} size="xs">All events</Anchor>
      </Group>
    </Stack>
  );
}

/** Check and run (D-121): the plan is made when the dialog opens (that changes nothing), its
 *  steps and warnings are shown, then one confirmation approves and runs it. */
function CheckAndRun({ opened, onClose, plan, checking, error, device }: {
  opened: boolean; onClose: () => void; plan?: StagingPlan; checking: boolean; error: Error | null; device: Device;
}) {
  const problem = plan?.steps.find((s) => s.state !== 'awaiting_approval' && s.state !== 'ready');
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title={`Check and run: ${device.name}`}>
      {checking && <Stack gap="xs"><Text size="sm">Checking the files, the image and the device. Nothing is changed.</Text><LoadingLines lines={3} /></Stack>}
      {error && <Stack><DialogError error={error} /><Group justify="flex-end"><Button onClick={onClose} data-autofocus>Close</Button></Group></Stack>}
      {plan && problem && (
        <Stack>
          <Notice kind="error" title="The check found a problem. Nothing was changed.">{failureReason(plan.steps)?.text ?? problem.state}</Notice>
          <Group justify="flex-end">
            <Button variant="default" component={Link} to={paths.plan(problem.id)}>Open the step</Button>
            <Button onClick={onClose} data-autofocus>Close</Button>
          </Group>
        </Stack>
      )}
      {plan && !problem && (
        <ApproveRunBody stagingId={plan.staging_id} steps={plan.steps} device={device}
          mode={plan.steps.some((x) => x.state === 'awaiting_approval') ? 'both' : 'run'} onCancel={onClose} onDone={onClose} />
      )}
    </Modal>
  );
}

function DeviceRun({ projectId, role, device, choice, latest, all }: {
  projectId: string; role: Role; device: Device; choice: Choice; latest?: StagingIndex; all: { device: Device }[];
}) {
  const [fresh, setFresh] = useState(false);
  // Its file moves it to an address another device of the system already has (both 2930F).
  const taken = choice.fileId ? addressTakenBy(role, device, all) : undefined;
  const { steps, missing } = planSteps(role, choice, device, taken);
  const parked = portOff(device);
  const consoleTodo = role.steps.includes('console') && !CONSOLE_DONE.has(device.provisioning_status);
  const make = useAction(() => api.createDeviceStaging(projectId, { device_id: device.id, steps }),
    (p) => `Plan made for ${device.name}: ${p.steps.length} steps waiting for approval`, { errorInDialog: true });
  const [checkOpen, { open: openCheck, close: closeCheck }] = useDisclosure();
  const check = useAction(() => api.createDeviceStaging(projectId, { device_id: device.id, steps }), undefined, { errorInDialog: true });
  const finished = latest && latest.states.every((x) => x === 'succeeded');
  const canMake = steps.length > 0 && missing.length === 0 && !consoleTodo;
  const usable = latest && !fresh;
  const takenNotice = taken && !(finished && !fresh) && (canMoveAside(taken) ? (
    <Notice kind="status" compact>
      Its file moves it to {role.addressAfter}, where {taken.name} answers. Stage {taken.name} first. This plan then
      switches off {taken.name}’s management port until its next power-on (nothing is saved on it): no cable to unplug.
    </Notice>
  ) : (
    <Notice kind="caution" compact>
      Its file moves it to {role.addressAfter}, where {taken.name} answers. Unplug {taken.name} from the small switch
      before you run this plan. If it still answers there, the file step stops before sending (nothing changed).
    </Notice>
  ));
  return (
    <Card id={`device-${device.id}`} style={{ scrollMarginTop: 72 }}>
      <Group justify="space-between" mb="xs" wrap="nowrap" align="flex-start">
        <div>
          <Title order={2}>{device.name}</Title>
          <Text size="xs" c="dimmed">{role.title} · {role.consoleCable
            ? `console ${device.console_port || '(port saved by its first access)'}` : device.management_address}</Text>
        </div>
        <Group gap={4} wrap="nowrap">
          {finished && !fresh && <Tag tone="success" icon={<IconCheck size={12} aria-hidden />}>Staged</Tag>}
          <Menu position="bottom-end" withinPortal>
            <Menu.Target><ActionIcon variant="subtle" color="gray" aria-label={`More for ${device.name}`}><IconDots size={16} /></ActionIcon></Menu.Target>
            <Menu.Dropdown>
              {latest && <Menu.Item component={Link} to={paths.staging(latest.staging_id)}>Open the plan</Menu.Item>}
              {usable && <Menu.Item onClick={() => setFresh(true)}>Make a new plan…</Menu.Item>}
              {!usable && <Menu.Item disabled={!canMake} onClick={() => make.mutate(undefined, { onSuccess: () => setFresh(false) })}>
                Make the plan only (approve and run later)</Menu.Item>}
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>
      <CheckAndRun opened={checkOpen} onClose={closeCheck} plan={check.data} checking={check.isPending} error={check.error} device={device} />
      {parked && <Notice kind="settled" compact mb="xs">Port {parked} off until its next power-on, to leave {device.management_address} free.
        Its saved configuration is unchanged: switch it off and on before it leaves the bench.</Notice>}
      {usable ? (
        <Stack gap="xs">
          {takenNotice}
          <LivePlan stagingId={latest.staging_id} onRetry={() => setFresh(true)} />
        </Stack>
      ) : (
        <Stack gap="xs">
          <PlannedSteps role={role} choice={choice} device={device} />
          {takenNotice}
          {consoleTodo && (
            <Notice kind="caution" compact action={<Button size="xs" variant="light" component={Link} to={paths.stage(device.project_id, 3, { console: device.id })}
              leftSection={<IconTerminal2 size={14} />}>Open console setup</Button>}>
              {role.consoleCable
                ? <>Do its first access first: UNDM starts it once without its factory configuration and sets the admin password. You switch it off and on when asked. It saves the console port this plan uses.</>
                : <>Do its console setup first (new switch, or a preconfigured one: tick “erase first” there), so it answers at {device.management_address}.</>}
            </Notice>
          )}
          {missing.length > 0 && <InlineStatus tone="warning">Still needed: {missing.join(', ')} (step 2).</InlineStatus>}
          <DialogError error={make.error} />
          <Group align="flex-start">
            <ReasonButton size="xs" color="orange" disabled={!canMake} loading={check.isPending}
              reason={consoleTodo ? (role.consoleCable ? 'Its first access comes first.' : 'Its console setup comes first.')
                : missing.length > 0 ? 'Choose what is still needed in step 2.' : steps.length === 0 ? 'Nothing to do: choose a file or an image in step 2.' : null}
              onClick={() => { check.reset(); openCheck(); check.mutate(undefined, { onSuccess: () => setFresh(false) }); }}>Check and run…</ReasonButton>
            {fresh && latest && <Button size="xs" variant="subtle" onClick={() => setFresh(false)}>Back to the last plan</Button>}
          </Group>
          <Text size="xs" c="dimmed">{role.consoleCable
            ? 'The check logs in over its console and reads its configuration; it changes nothing. Then one confirmation approves and runs it: the lines go one at a time, and the load stops, unsaved, at the first line the modem refuses.'
            : 'The check reads the files, the image and the device, and changes nothing. Then one confirmation approves and runs it.'}</Text>
        </Stack>
      )}
    </Card>
  );
}

/** Step 4: one card per device: make the plan, approve, run, follow. */
export function RunStep({ projectId, roles, choices, stagings }: {
  projectId: string; roles: { role: Role; device: Device }[]; choices: Partial<Record<string, Choice>>; stagings: StagingIndex[];
}) {
  const [startAll, { open: openStartAll, close: closeStartAll }] = useDisclosure();
  // A link to one device's card (the report's "Still to do") scrolls to it once the cards are there.
  const { hash } = useLocation();
  useEffect(() => {
    if (hash.startsWith('#device-')) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' });
  }, [hash, roles.length]);
  if (roles.length === 0) return <EmptyState>Add the devices first (step 1: System and devices).</EmptyState>;
  const order = startOrder(roles, choices, stagings);
  const ready = order.filter((i) => i.ready).length;
  return (
    <Stack>
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <Text size="sm" c="dimmed" maw={760}>Devices run independently: start one while another restarts. The runs continue on the
          server if you leave this page. Two devices that end at the same address (the two 2930F) run one after the other.</Text>
        <ReasonButton variant={ready > 0 ? "filled" : "default"} leftSection={<IconPlayerPlay size={16} />} disabled={order.length === 0}
          reason={order.length === 0 ? 'Every device is staged or staged by hand.' : null}
          onClick={openStartAll}>Start all ready ({ready})…</ReasonButton>
      </Group>
      <StartAllDialog opened={startAll} onClose={closeStartAll} projectId={projectId} items={order} />
      <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }}>
        {roles.map(({ role, device }) => (role.guided ? (
          <GuidedRun key={role.key} role={role} device={device} choice={choices[role.key] ?? EMPTY_CHOICE} />
        ) : (
          <DeviceRun key={role.key} projectId={projectId} role={role} device={device}
            choice={choices[role.key] ?? EMPTY_CHOICE}
            latest={stagings.find((x) => x.device_id === device.id)} all={roles} />
        )))}
      </SimpleGrid>
    </Stack>
  );
}

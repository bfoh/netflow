import { Checkbox, Group, Stack, Text, TextInput } from '@mantine/core';

import { Notice } from '../../components/Notice';
import type { ApprovalWindow } from './window';
import { windowProblem } from './window';

/**
 * What an approval asks for, the same in every place (D-121): the maintenance window when a
 * firmware step waits, and who approves. The person who made a firmware plan approves it alone
 * only by ticking "I am staging alone".
 */
export function ApproveFields({ firmware, window, onWindow, maker, actor, second, soloOffered, solo, onSolo }: {
  firmware: boolean;
  window: ApprovalWindow;
  onWindow: (w: ApprovalWindow) => void;
  maker?: string;
  actor: string;
  /** A second person must approve, and the person approving made the plan. */
  second: boolean;
  soloOffered: boolean;
  solo: boolean;
  onSolo: (v: boolean) => void;
}) {
  if (!firmware) return null;
  const problem = windowProblem(window);
  return (
    <Stack gap="xs">
      <Text size="sm">Its firmware step may only run inside an approved window (times in UTC, at most 24 hours).</Text>
      <Group grow align="flex-start">
        <TextInput type="datetime-local" label="From (UTC)" value={window.start} onChange={(e) => onWindow({ ...window, start: e.currentTarget.value })} />
        <TextInput type="datetime-local" label="Until (UTC)" value={window.end} onChange={(e) => onWindow({ ...window, end: e.currentTarget.value })}
          error={problem ?? undefined} />
      </Group>
      {maker && maker !== actor && <Text size="sm" c="dimmed">You approve as the second person: {maker} made this plan.</Text>}
      {second && (soloOffered ? (
        <Checkbox checked={solo} onChange={(e) => onSolo(e.currentTarget.checked)} label="I am staging alone"
          description={`Firmware plans need a second person to approve them, and you (${actor}) made this one. Ticked, that rule is switched off for this approval and on again at once; both are recorded in the audit log.`} />
      ) : (
        <Notice kind="caution" compact>
          A second person must approve this firmware plan: you ({actor}) made it, and the rule is fixed in the start-up file.
          Ask a colleague to approve it under their name.
        </Notice>
      ))}
    </Stack>
  );
}

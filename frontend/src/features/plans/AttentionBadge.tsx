import { Group, Tooltip } from '@mantine/core';

import { StateBadge, Tag } from '../../components/Badges';
import type { DeploymentSummary } from '../../types/api';

/** A plan's status; a plan that needed attention also says why it no longer waits (D-088). */
export function PlanStatus({ d }: { d: Pick<DeploymentSummary, 'state' | 'attention_cleared'> }) {
  const cleared = d.attention_cleared;
  if (d.state !== 'recovery_required' || !cleared) return <StateBadge state={d.state} />;
  const checked = cleared === 'checked';
  return (
    <Group gap={4} wrap="nowrap">
      <StateBadge state={d.state} />
      <Tooltip withArrow multiline w={260} label={checked
        ? 'A person checked the device and recorded what they found (see the plan\'s events).'
        : 'A later plan on the same device(s) succeeded, so the device was checked again.'}>
        <Tag tone="neutral">{checked ? 'checked' : 'later plan succeeded'}</Tag>
      </Tooltip>
    </Group>
  );
}

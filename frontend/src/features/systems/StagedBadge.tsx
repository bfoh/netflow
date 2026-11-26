import { Badge, Tooltip } from '@mantine/core';

import { fmtDate } from '../../services/format';
import type { Project } from '../../types/api';

/** "Staged <date>" for a system whose staging was finished (D-108); nothing otherwise. */
export function StagedBadge({ project }: { project: Project }) {
  if (!project.staged_at) return null;
  const day = fmtDate(project.staged_at).split(' ')[0];
  return (
    <Tooltip label={`Staging finished ${fmtDate(project.staged_at)}${project.staged_by ? ` by ${project.staged_by}` : ''}`}>
      <Badge color="teal" variant="light" tt="none" radius="sm">Staged {day}</Badge>
    </Tooltip>
  );
}

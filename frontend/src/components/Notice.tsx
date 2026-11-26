import { Alert, Anchor, Collapse, Group, Stack, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconAlertTriangle, IconCircleCheck, IconInfoCircle, IconLoader2, IconX } from '@tabler/icons-react';
import type { ReactNode } from 'react';

/**
 * The only way a page shows a message box (D-089). Four kinds, each with one colour and icon:
 *  - error:   something is wrong or blocks you; say how to fix it (red)
 *  - caution: a risk to weigh at the point of action (amber)
 *  - status:  what a run is doing or how it ended (blue while running, grey when settled)
 *  - success: it worked (teal)
 * Explanations are not messages: use Hint. Empty lists: use EmptyState.
 */
export type NoticeKind = 'error' | 'caution' | 'status' | 'settled' | 'success';

const LOOK: Record<NoticeKind, { color: string; icon: ReactNode }> = {
  error: { color: 'red', icon: <IconX size={18} /> },
  caution: { color: 'orange', icon: <IconAlertTriangle size={18} /> },
  status: { color: 'blue', icon: <IconLoader2 size={18} /> },
  settled: { color: 'gray', icon: <IconInfoCircle size={18} /> },
  success: { color: 'teal', icon: <IconCircleCheck size={18} /> },
};

/** How screen readers hear each kind (WCAG 4.1.3): errors interrupt; running status and
 *  success are announced politely; cautions and settled facts are read in place. */
const ROLE: Record<NoticeKind, string> = {
  error: 'alert', status: 'status', success: 'status', caution: 'note', settled: 'note',
};

export function Notice({ kind, title, children, action, details, compact, mb, mt, role, live = true }: {
  kind: NoticeKind;
  title?: ReactNode;
  children?: ReactNode;
  /** The next step, e.g. a button or link. */
  action?: ReactNode;
  /** Longer text, folded under "More". */
  details?: ReactNode;
  compact?: boolean;
  mb?: string | number;
  mt?: string | number;
  role?: string;
  /** false: content that changes by itself (a ticking timer) is not announced each time. */
  live?: boolean;
}) {
  const [open, { toggle }] = useDisclosure(false);
  const look = LOOK[kind];
  return (
    <Alert color={look.color} icon={look.icon} title={title} p={compact ? 'xs' : undefined} mb={mb} mt={mt}
      role={role ?? (live ? ROLE[kind] : 'note')}>
      <Stack gap={6}>
        {children && <Text size="sm" component="div" style={{ wordBreak: 'break-word' }}>{children}</Text>}
        {(action || details) && (
          <Group gap="sm" justify="space-between" wrap="wrap">
            {details ? <Anchor component="button" type="button" size="xs" onClick={toggle} aria-expanded={open}>{open ? 'Less' : 'More'}</Anchor> : <span />}
            {action}
          </Group>
        )}
        {details && <Collapse expanded={open}><Text size="xs" component="div">{details}</Text></Collapse>}
      </Stack>
    </Alert>
  );
}

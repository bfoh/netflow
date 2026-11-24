import { Stack, Text, ThemeIcon } from '@mantine/core';
import { IconInbox } from '@tabler/icons-react';
import type { ReactNode } from 'react';

/** Nothing to show yet: what that means and the next step (D-089). Not a message box. */
export function EmptyState({ children, action, icon }: { children: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <Stack align="center" gap="xs" py="xl">
      <ThemeIcon size={40} radius="xl" variant="light" color="gray">{icon ?? <IconInbox size={22} />}</ThemeIcon>
      <Text size="sm" c="dimmed" ta="center" maw={420}>{children}</Text>
      {action}
    </Stack>
  );
}

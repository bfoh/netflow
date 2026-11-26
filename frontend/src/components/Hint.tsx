import { Anchor, Box, Collapse, Group, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconInfoCircle } from '@tabler/icons-react';
import type { ReactNode } from 'react';

/** An explanation: small, quiet text with an ⓘ, never a box (D-089). `more` folds the rest. */
export function Hint({ children, more, icon, mb, mt }: {
  children: ReactNode; more?: ReactNode; icon?: ReactNode; mb?: string | number; mt?: string | number;
}) {
  const [open, { toggle }] = useDisclosure(false);
  return (
    <Box mb={mb} mt={mt}>
      <Group gap={6} wrap="nowrap" align="flex-start">
        <Box c="dimmed" style={{ lineHeight: 0, paddingTop: 2 }}>{icon ?? <IconInfoCircle size={14} />}</Box>
        <Text size="xs" c="dimmed" component="div">
          {children}
          {more && <> <Anchor component="button" type="button" size="xs" onClick={toggle} aria-expanded={open}>{open ? 'Less' : 'More'}</Anchor></>}
        </Text>
      </Group>
      {more && <Collapse expanded={open}><Text size="xs" c="dimmed" component="div" pl={20} pt={4}>{more}</Text></Collapse>}
    </Box>
  );
}

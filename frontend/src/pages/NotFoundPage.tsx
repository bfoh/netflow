import { Button, Group, Stack, Text } from '@mantine/core';
import { Link, useLocation } from 'react-router';

import { PageHeader } from '../components/Page';
import { paths } from '../paths';

/** An address UNDM does not have: say so, and offer the two places most work starts (D-120). */
export function NotFoundPage() {
  const { pathname } = useLocation();
  return (
    <Stack maw={640} gap="md">
      <PageHeader title="Page not found" description={`UNDM has no page at ${pathname}. A link may be out of date.`} />
      <Text size="sm">Use the menu on the left, or go to one of these:</Text>
      <Group>
        <Button component={Link} to={paths.home}>Go to Home</Button>
        <Button variant="default" component={Link} to={paths.stage()}>Stage a system</Button>
      </Group>
    </Stack>
  );
}

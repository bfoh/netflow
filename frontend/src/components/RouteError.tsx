import { Button, Code, Group, Stack, Text, Title } from '@mantine/core';
import { isRouteErrorResponse, Link, useRouteError } from 'react-router';

import { Notice } from './Notice';
import { paths } from '../paths';

/** Shown instead of a page that crashed, inside the normal layout so navigation keeps working. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error ? error.message : String(error);
  return (
    <Stack maw={720} gap="md">
      <Title order={1}>This page hit an error</Title>
      <Notice kind="error">Something went wrong while showing this page. Your data has not been changed.</Notice>
      <Code block>{message}</Code>
      <Text size="sm" c="dimmed">Please report what you clicked just before this happened, together with the message above.</Text>
      <Group>
        <Button component={Link} to={paths.home}>Go to Home</Button>
        <Button variant="default" onClick={() => window.location.reload()}>Reload page</Button>
      </Group>
    </Stack>
  );
}

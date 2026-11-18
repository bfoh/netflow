import { Alert, Button, Code, Group, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { isRouteErrorResponse, Link, useRouteError } from 'react-router';

/** Shown instead of a page that crashed, inside the normal layout so navigation keeps working. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error ? error.message : String(error);
  return (
    <Stack maw={720} gap="md">
      <Title order={2}>This page hit an error</Title>
      <Alert color="red" icon={<IconAlertTriangle size={18} />}>
        <Text size="sm">Something went wrong while showing this page. Your data has not been changed.</Text>
      </Alert>
      <Code block>{message}</Code>
      <Text size="sm" c="dimmed">Please report what you clicked just before this happened, together with the message above.</Text>
      <Group>
        <Button component={Link} to="/">Go to dashboard</Button>
        <Button variant="default" onClick={() => window.location.reload()}>Reload page</Button>
      </Group>
    </Stack>
  );
}

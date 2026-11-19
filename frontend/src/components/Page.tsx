import { Alert, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import type { ReactNode } from 'react';

export function PageHeader({ title, description, actions }:
  { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-start" mb="lg" wrap="wrap">
      <Stack gap={4}>
        <Title order={2}>{title}</Title>
        {description && <Text c="dimmed" size="sm">{description}</Text>}
      </Stack>
      {actions && <Group gap="sm">{actions}</Group>}
    </Group>
  );
}

export function QueryState({ isLoading, error }: { isLoading: boolean; error: Error | null }) {
  if (isLoading) return <Group justify="center" p="xl"><Loader size="sm" /></Group>;
  if (error) {
    return (
      <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Could not load data">
        {error.message}
      </Alert>
    );
  }
  return null;
}

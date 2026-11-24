import { Group, Loader, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

import { Notice } from './Notice';

export function PageHeader({ title, description, actions }:
  { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-start" mb="lg" wrap="wrap">
      <Stack gap={4}>
        <Title order={1} size="h2">{title}</Title>
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
      <Notice kind="error" title="Could not load this page's data">{error.message}</Notice>
    );
  }
  return null;
}

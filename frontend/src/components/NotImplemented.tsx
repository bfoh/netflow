import { Card, List, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconHammer } from '@tabler/icons-react';

export function NotImplemented({ title, phase, planned, note }:
  { title: string; phase: string; planned: string[]; note?: string }) {
  return (
    <Card withBorder padding="xl" radius="md">
      <Stack gap="md" align="flex-start">
        <ThemeIcon size="xl" variant="light" color="gray"><IconHammer /></ThemeIcon>
        <Title order={2} size="h3">{title} is not implemented yet</Title>
        <Text c="dimmed">
          Planned for {phase}. {note ?? 'Nothing on this page performs an operation today.'}
        </Text>
        <List size="sm" spacing={4}>
          {planned.map((p) => <List.Item key={p}>{p}</List.Item>)}
        </List>
      </Stack>
    </Card>
  );
}

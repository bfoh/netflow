import { ActionIcon, Anchor, Breadcrumbs, Group, Menu, Skeleton, Stack, Text, Title } from '@mantine/core';
import { IconDots } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { Notice } from './Notice';

export interface Crumb { label: string; to?: string }

/**
 * The top of every page (D-119): where you are, what this page is for, and what you do here.
 * One primary action at most; a second one if it is common; everything else in "More".
 */
export function PageHeader({ title, description, badges, primary, secondary, menu, breadcrumbs, actions }: {
  title: string;
  description?: ReactNode;
  /** State shown next to the title (e.g. Staged). */
  badges?: ReactNode;
  /** The main thing to do on this page (a filled button). */
  primary?: ReactNode;
  /** A common second action (a default button). */
  secondary?: ReactNode;
  /** Less frequent actions, as Menu.Item elements under "More". */
  menu?: ReactNode;
  breadcrumbs?: Crumb[];
  /** Deprecated: free-form actions, kept while pages move to primary/secondary/menu. */
  actions?: ReactNode;
}) {
  useDocumentTitle(title);
  return (
    <Stack gap={6} mb="lg">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs separatorMargin={6} aria-label="Breadcrumbs">
          {breadcrumbs.map((c) => (c.to
            ? <Anchor key={c.label} component={Link} to={c.to} size="sm">{c.label}</Anchor>
            : <Text key={c.label} size="sm" c="dimmed">{c.label}</Text>))}
        </Breadcrumbs>
      )}
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="sm">
        <Stack gap={4} style={{ minWidth: 0, flex: '1 1 320px' }}>
          <Group gap="sm" wrap="wrap">
            <Title order={1} id="page-title" tabIndex={-1} style={{ outline: 'none' }}>{title}</Title>
            {badges}
          </Group>
          {description && <Text c="dimmed" size="sm" maw={820}>{description}</Text>}
        </Stack>
        {(primary || secondary || menu || actions) && (
          <Group gap="sm" wrap="wrap">
            {actions}
            {secondary}
            {primary}
            {menu && (
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="More actions"><IconDots size={18} /></ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>{menu}</Menu.Dropdown>
              </Menu>
            )}
          </Group>
        )}
      </Group>
    </Stack>
  );
}

/** Placeholder lines while a page or card loads: never "nothing yet" before the data is here. */
export function LoadingLines({ lines = 3 }: { lines?: number }) {
  return (
    <Stack gap="xs" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} height={14} width={i === lines - 1 ? '60%' : '100%'} />)}
    </Stack>
  );
}

export function QueryState({ isLoading, error }: { isLoading: boolean; error: Error | null }) {
  if (isLoading) return <LoadingLines lines={4} />;
  if (error) {
    return (
      <Notice kind="error" title="Could not load this page's data">{error.message}</Notice>
    );
  }
  return null;
}

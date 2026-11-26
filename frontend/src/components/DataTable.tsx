import { Table } from '@mantine/core';
import type { ReactNode } from 'react';

import { EmptyState } from './EmptyState';
import { Notice } from './Notice';
import { LoadingLines } from './Page';

/** A table with its states in order (D-119): loading lines, then an error, then "nothing
 *  yet" only once the data has arrived, then the rows. It is named for screen readers. */
export function DataTable({ label, loading, error, rowCount, empty, emptyAction, minWidth = 600, children, highlight = true }: {
  /** What the table lists, e.g. "Plans of this system". */
  label: string;
  loading?: boolean;
  error?: Error | null;
  rowCount: number;
  /** What an empty table means and what to do. */
  empty: ReactNode;
  emptyAction?: ReactNode;
  minWidth?: number;
  /** Table.Thead and Table.Tbody. */
  children: ReactNode;
  highlight?: boolean;
}) {
  if (loading) return <LoadingLines lines={4} />;
  if (error) return <Notice kind="error" title="Could not load this list">{error.message}</Notice>;
  if (rowCount === 0) return <EmptyState action={emptyAction}>{empty}</EmptyState>;
  return (
    <Table.ScrollContainer minWidth={minWidth}>
      <Table aria-label={label} highlightOnHover={highlight}>{children}</Table>
    </Table.ScrollContainer>
  );
}

/** The name of a column that holds only buttons: read by screen readers, not shown. */
export function ActionsHeader({ label = 'Actions' }: { label?: string }) {
  return <Table.Th><span className="undm-visually-hidden">{label}</span></Table.Th>;
}

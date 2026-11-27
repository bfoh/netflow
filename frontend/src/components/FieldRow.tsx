import { Box, type BoxProps, Group, type GroupProps } from '@mantine/core';
import type { ComponentPropsWithoutRef } from 'react';

/** The height of a field's label line (one line in the page's base font): what sits beside a
 *  field starts this much lower, so it lines up with the input box. */
export const LABEL_LINE = 'calc(var(--mantine-font-size-md) * var(--mantine-line-height))';
const CONTROL = 'calc(2.25rem * var(--mantine-scale))';

/**
 * A row of fields with buttons or a status beside them (v96). Everything aligns at the top,
 * so what a field or a button shows under itself (a description, an error, a reason) never
 * moves the rest of the row. Put whatever is not a field in {@link Beside}.
 */
export function FieldRow(props: GroupProps) {
  return <Group align="flex-start" wrap="wrap" {...props} />;
}

/** Something beside fields in a {@link FieldRow}: starts at the input box and is centred on
 *  it (a button, a short status). */
export function Beside(props: Omit<BoxProps, 'style'> & Omit<ComponentPropsWithoutRef<'div'>, 'style'>) {
  return <Box {...props} style={{ marginTop: LABEL_LINE, minHeight: CONTROL, display: 'flex', alignItems: 'center' }} />;
}

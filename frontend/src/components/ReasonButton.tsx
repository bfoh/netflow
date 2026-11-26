import { Button, type ButtonProps, Stack, Text } from '@mantine/core';
import { type ComponentPropsWithoutRef, useId } from 'react';

/** A button that says why it cannot be pressed (D-119): the reason is visible text, linked
 *  to the button for screen readers. Nobody has to guess what is missing. */
export function ReasonButton({ reason, disabled, ...props }: ButtonProps & ComponentPropsWithoutRef<'button'> & {
  /** Why it is disabled; shown only while it is. */
  reason?: string | null;
}) {
  const id = useId();
  const off = !!disabled;
  const why = off && reason ? reason : null;
  return (
    <Stack gap={4} align="flex-start">
      <Button {...props} disabled={off} aria-describedby={why ? id : undefined} />
      {why && <Text id={id} size="xs" c="dimmed">{why}</Text>}
    </Stack>
  );
}

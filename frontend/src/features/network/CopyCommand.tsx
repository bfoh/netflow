import { Button, Code, CopyButton, Group } from '@mantine/core';

/** A command or line to copy as it is: UNDM shows it, the person runs or pastes it. */
export function CopyCommand({ value, label }: { value: string; label?: string }) {
  return (
    <Group gap="xs" wrap="nowrap" align="flex-start">
      <Code block style={{ flex: 1, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{value}</Code>
      <CopyButton value={value}>
        {({ copied, copy }) => (
          <Button size="xs" variant="default" onClick={copy} aria-label={label ? `Copy ${label}` : 'Copy'}>
            {copied ? 'Copied' : 'Copy'}</Button>
        )}
      </CopyButton>
    </Group>
  );
}

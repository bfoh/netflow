import { Code, Text } from '@mantine/core';

import classes from '../styles/diff.module.css';

/** Renders a unified diff with added/removed lines highlighted. */
export function DiffView({ diff }: { diff: string }) {
  if (!diff) return <Text c="dimmed" size="sm">No differences.</Text>;
  return (
    <Code block className={classes.diff}>
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+++') || line.startsWith('---') ? classes.meta
          : line.startsWith('+') ? classes.add
          : line.startsWith('-') ? classes.del
          : line.startsWith('@@') ? classes.meta : undefined;
        return <div key={i} className={cls}>{line || ' '}</div>;
      })}
    </Code>
  );
}

import { Button, Code, CopyButton, Group, Modal, SegmentedControl, Stack } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { IconCopy, IconDownload, IconFileText } from '@tabler/icons-react';
import { useState } from 'react';

import { Notice } from '../../components/Notice';
import { QueryState } from '../../components/Page';
import { api } from '../../services/api';
import { downloadText } from '../../services/format';

/** A masked text of everything recorded about the system's devices, to send instead of
 *  screenshots (D-090). Shown first, so it can be read before it is shared. */
export function BenchLogButton({ projectId, size = 'sm' }: { projectId: string; size?: 'xs' | 'sm' }) {
  const [opened, { open, close }] = useDisclosure();
  const [hours, setHours] = useState('48');
  const log = useQuery({ queryKey: ['bench-log', projectId, hours], queryFn: () => api.benchLog(projectId, Number(hours)),
    enabled: opened, staleTime: 0 });
  return (
    <>
      <Button size={size} variant="default" leftSection={<IconFileText size={16} />} onClick={open}>Bench log…</Button>
      <Modal opened={opened} onClose={close} title="Bench log" size="xl">
        <Stack>
          <Notice kind="caution" compact title="Read it through before sharing">
            Addresses, MAC addresses, serial numbers, names and logins are replaced with placeholders such as &lt;device-1&gt;.
            Masking is automatic and best effort.
          </Notice>
          <SegmentedControl size="xs" aria-label="Time covered" value={hours} onChange={setHours}
            data={[{ value: '24', label: 'Last 24 h' }, { value: '48', label: 'Last 48 h' }, { value: '0', label: 'Everything' }]} />
          <QueryState isLoading={log.isLoading} error={log.error} />
          {log.data && <Code block mah={420} style={{ overflow: 'auto', fontSize: 11, whiteSpace: 'pre-wrap' }}>{log.data}</Code>}
          <Group justify="flex-end">
            <CopyButton value={log.data ?? ''}>
              {({ copied, copy }) => <Button variant="default" leftSection={<IconCopy size={16} />} disabled={!log.data}
                onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>}
            </CopyButton>
            <Button leftSection={<IconDownload size={16} />} disabled={!log.data}
              onClick={() => downloadText(`undm-bench-log-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.txt`, log.data ?? '')}>Download .txt</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

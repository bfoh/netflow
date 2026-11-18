import { Alert, Button, Code, CopyButton, Group, Modal, Stack, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconFileReport, IconShieldCheck } from '@tabler/icons-react';
import { useState } from 'react';

import { api } from '../../services/api';
import { downloadText } from '../../services/format';
import type { Device } from '../../types/api';

/** Shows a sanitized report of the last retrieved device information, ready to share. */
export function DiagnosticsButton({ device }: { device: Device }) {
  const [opened, { open, close }] = useDisclosure();
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    setError('');
    try {
      setText((await api.diagnostics(device.id)).text);
      open();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const download = () => downloadText(`undm-diagnostics-${device.os_family || 'device'}.txt`, text);
  return (
    <>
      <Button size="xs" variant="light" leftSection={<IconFileReport size={14} />} loading={busy} onClick={load}>Sanitized diagnostics</Button>
      {error && <Text size="xs" c="red">{error}</Text>}
      <Modal opened={opened} onClose={close} title="Sanitized diagnostics" size="xl">
        <Stack>
          <Alert color="blue" icon={<IconShieldCheck size={18} />}>
            IP addresses, MAC addresses, serial numbers, names, contacts, locations and secrets are replaced with placeholders.
            Masking is automatic and best effort: <b>read it through before sharing</b>.
          </Alert>
          <Code block mah={420} style={{ overflow: 'auto', fontSize: 12 }}>{text}</Code>
          <Group justify="flex-end">
            <CopyButton value={text}>{({ copied, copy }) => <Button variant="default" onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>}</CopyButton>
            <Button leftSection={<IconDownload size={16} />} onClick={download}>Download .txt</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

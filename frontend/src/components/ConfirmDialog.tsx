import { Alert, Button, Group, Modal, Stack, Text, TextInput } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { type ReactNode, useState } from 'react';

/** An error shown inside the dialog that caused it, so it cannot be missed or lost. */
export function DialogError({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return (
    <Alert color="red" icon={<IconAlertTriangle size={16} />} title="That did not work" role="alert">
      <Text size="sm" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{error.message}</Text>
    </Alert>
  );
}

export interface ConfirmRequest {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  /** red for destructive or device-changing actions (default), otherwise e.g. 'blue'. */
  color?: string;
  /** If set, the person must type this text before the action is allowed. */
  typed?: string;
  /** May return a promise; an error it throws is shown in the dialog, which stays open. */
  onConfirm: () => unknown;
}

export function ConfirmDialog({ req, onClose }: { req: ConfirmRequest; onClose: () => void }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const ready = !req.typed || text.trim() === req.typed;
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await req.onConfirm();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal opened onClose={onClose} title={req.title}>
      <Stack>
        <Text size="sm" component="div">{req.message}</Text>
        {req.typed && (
          <TextInput label={`Type ${req.typed} to confirm`} value={text} data-autofocus
            onChange={(e) => setText(e.currentTarget.value)} autoComplete="off" />
        )}
        <DialogError error={error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Back</Button>
          <Button color={req.color ?? 'red'} disabled={!ready} loading={busy} onClick={() => void go()}>{req.confirmLabel}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

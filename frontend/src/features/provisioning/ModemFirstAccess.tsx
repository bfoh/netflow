import { Badge, Button, Card, Code, CopyButton, Group, List, Modal, Select, Stack, Text, TextInput, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconRefresh, IconTerminal2 } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { Notice, type NoticeKind } from '../../components/Notice';
import { SafetyHint } from '../../components/SafetyHint';
import { useAction, useCredentialRefs, usePolicy, useSerialPorts } from '../../hooks/queries';
import { api } from '../../services/api';
import { downloadText } from '../../services/format';
import type { BootstrapResult, Device } from '../../types/api';
import { paths } from '../../paths';

const BAUD = ['9600', '19200', '38400', '57600', '115200'];
/** What the run is doing, in words (stages of sros_sar.first_access). */
const STAGE_WORDS: Record<string, string> = {
  opening: 'Opening the console',
  listening: 'Waiting for the modem’s start-up: switch it off and on now',
  question_answered: 'Its 3-second question answered: Enter sent',
  boot_menu: 'Answering its boot menu',
  starting: 'The modem is starting without its configuration (about 2–3 minutes)',
  logged_in: 'Logged in with the factory login',
  commands: 'Setting the admin password and boot options',
  saved: 'Saved; reading its information',
  finished: 'Done',
};
const mmss = (s: number) => `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;

/** What UNDM sees on the console while the run is under way (polled). */
function Progress({ deviceId }: { deviceId: string }) {
  const p = useQuery({ queryKey: ['console-progress', deviceId], queryFn: () => api.consoleProgress(deviceId), refetchInterval: 2000 });
  const d = p.data;
  if (!d?.stage) return null;
  const words = d.stage === 'listening' && d.received > 0
    ? 'The modem is starting (its start-up text is arriving): UNDM answers its 3-second question by itself'
    : STAGE_WORDS[d.stage] ?? d.stage;
  return (
    <Stack gap={2} mt={4}>
      <Text size="sm"><b>{words}</b> · {mmss(d.seconds)} · {d.received.toLocaleString()} bytes received</Text>
      {d.last_line && <Text size="xs" ff="monospace" c="dimmed" lineClamp={1}>{d.last_line}</Text>}
    </Stack>
  );
}
const STATUS: Record<BootstrapResult['status'], { kind: NoticeKind; title: string }> = {
  bootstrapped: { kind: 'success', title: 'First access done' },
  already_configured: { kind: 'success', title: 'Already done — nothing was changed' },
  refused: { kind: 'caution', title: 'Refused — nothing was changed' },
  failed: { kind: 'error', title: 'First access did not finish' },
};

/** First access to a factory Nokia 7705 SAR-Hmc over its console cable (D-112). */
export function ModemFirstAccess({ device, simulated, back }: {
  device: Device; simulated: boolean;
  /** Inside Stage a system: the way back to its step, offered once the first access is done. */
  back?: { label: string; onClick: () => void };
}) {
  const ports = useSerialPorts();
  const policy = usePolicy();
  const refs = useCredentialRefs(device.project_id);
  const [serialPort, setSerialPort] = useState<string | null>(simulated ? 'SIMULATED' : null);
  const [baud, setBaud] = useState('115200');
  const [result, setResult] = useState<BootstrapResult | null>(null);
  const [confirm, setConfirm] = useState('');
  const [opened, { open, close }] = useDisclosure(false);
  const preview = useQuery({ queryKey: ['first-access-preview', device.id, device.credential_ref_id],
    queryFn: () => api.firstAccessPreview(device.id) });
  const chooseLogin = useAction((ref: string | null) => api.updateDevice(device.id, { credential_ref_id: ref }), 'Login chosen');
  const run = useAction(() => api.consoleBootstrap(device.id, {
    serial_port: serialPort!, baudrate: Number(baud), confirm_device_name: confirm, allow_configured: false,
  }), undefined, { errorInDialog: true });
  const blocked = !simulated && policy.data && !policy.data.enable_real_device_writes;
  const portOptions = (ports.data ?? []).filter((p) => (p.port === 'SIMULATED') === simulated)
    .map((p) => ({ value: p.port, label: p.description ? `${p.port} — ${p.description}` : p.port }));
  const before = (preview.data?.notes ?? []).find((n) => n.startsWith('Before you run: '));
  const done = result && (result.status === 'bootstrapped' || result.status === 'already_configured');

  return (
    <Stack>
      <Card withBorder>
        <Title order={2} size="h5" mb="xs">1 · Its login after the first access</Title>
        <Select label="Approved login (user name admin)" w="100%" maw={380} clearable
          description="Its password becomes the modem's admin password. The modem refuses a password it finds too simple."
          placeholder={refs.data?.length ? 'Choose the approved login' : "Add it on the system's Logins tab, or in Settings → Logins"}
          data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))}
          value={device.credential_ref_id} onChange={(v) => chooseLogin.mutate(v)} />
        {before && <Notice kind="error" compact mt="sm">{before.replace('Before you run: ', '')}</Notice>}
      </Card>

      <Card withBorder>
        <Title order={2} size="h5" mb="xs">2 · What UNDM does on the console</Title>
        <Text size="sm" c="dimmed" mb="xs">
          For a modem straight from the factory, which does not accept the default login. UNDM starts it once without its
          configuration and auto-discovery, logs in with the factory login, sets the admin password and saves.
        </Text>
        {preview.data && (
          <>
            <Code block mah={260} style={{ overflow: 'auto' }}>{preview.data.commands.join('\n')}</Code>
            <Hint more={<List size="xs" spacing={2}>{preview.data.notes.filter((n) => !n.startsWith('Before you run: '))
              .map((n) => <List.Item key={n}>{n}</List.Item>)}</List>}>
              UNDM answers only these questions, in this order. Experimental: not yet run by UNDM on a modem.
            </Hint>
          </>
        )}
      </Card>

      <Card withBorder>
        <Title order={2} size="h5" mb="xs">3 · Console connection</Title>
        <Group align="flex-end">
          <Select label="Serial port" w="100%" maw={380} placeholder={portOptions.length ? 'Choose the console cable’s port' : 'No serial ports found'}
            data={portOptions} value={serialPort} onChange={setSerialPort} />
          <Select label="Speed (baud)" w={130} data={BAUD} value={baud} onChange={(v) => setBaud(v ?? '115200')} disabled={simulated} allowDeselect={false} />
          <Button variant="default" leftSection={<IconRefresh size={14} />} onClick={() => void ports.refetch()} loading={ports.isFetching}>Refresh ports</Button>
        </Group>
        {!simulated && (
          <Text size="xs" c="dimmed" mt="xs">
            Connect the console cable to the modem, then refresh. Close PuTTY or any other terminal program first: only one
            program can use a COM port. A factory modem uses 115200, 8 data bits, no parity, 1 stop bit.
          </Text>
        )}
        <Group mt="md">
          <Button leftSection={<IconTerminal2 size={16} />} disabled={!serialPort || !!blocked || !!before || !device.credential_ref_id}
            onClick={() => { setConfirm(''); open(); }}>Run first access…</Button>
          <SafetyHint real={!simulated} />
        </Group>
      </Card>

      {result && (
        <Card withBorder>
          <Notice kind={STATUS[result.status].kind} title={STATUS[result.status].title} mb="sm">
            {result.message}
            {result.findings.length > 0 && <List size="sm" mt={4}>{result.findings.map((f) => <List.Item key={f}>{f}</List.Item>)}</List>}
            {result.network_hint && <Text size="sm" mt={6}>{result.network_hint}</Text>}
          </Notice>
          <Group gap="xs" mb="xs">
            {result.password_set && <Badge variant="light" color="teal" tt="none">admin password set</Badge>}
            <Badge variant="light" color={result.saved ? 'teal' : 'gray'} tt="none">{result.saved ? 'boot options and configuration saved' : 'not saved'}</Badge>
            <Badge variant="light" color={result.verified ? 'teal' : 'gray'} tt="none">{result.verified ? 'read back and verified' : 'not verified'}</Badge>
            {result.facts?.type && <Badge variant="light" color="gray" tt="none">{result.facts.type} · {result.facts.version ?? ''}</Badge>}
          </Group>
          <Text size="sm" fw={600}>Console transcript</Text>
          <Code block mah={360} style={{ overflow: 'auto', fontSize: 11 }}>{result.transcript}</Code>
          {result.diagnostics && Object.keys(result.diagnostics).length > 0 && (
            <Hint more={<Code block mah={240} style={{ overflow: 'auto', fontSize: 11 }}>
              {Object.entries(result.diagnostics).map(([k, v]) => `${k}:${v.includes('\n') ? '\n' : ' '}${v}`).join('\n\n')}</Code>}>
              Technical details: what the console sent around the question, control characters written out (\r, \b, \x00). They
              are included when you copy or download the sanitized transcript.
            </Hint>
          )}
          <Group mt="xs">
            <CopyButton value={result.sanitized_transcript}>{({ copied, copy }) => <Button size="xs" variant="default" onClick={copy}>{copied ? 'Copied' : 'Copy sanitized transcript'}</Button>}</CopyButton>
            <Button size="xs" variant="default" leftSection={<IconDownload size={14} />}
              onClick={() => downloadText('undm-modem-first-access-sanitized.txt', result.sanitized_transcript)}>Download sanitized transcript</Button>
            {done && (back
              ? <Button size="xs" onClick={back.onClick}>{back.label}</Button>
              : <Button size="xs" component={Link} to={paths.stage(device.project_id, 3)}>Back to Stage a system</Button>)}
          </Group>
        </Card>
      )}

      <Modal opened={opened} onClose={close} title={`First access: ${device.name}`} size="lg">
        <Stack>
          <List size="sm" type="ordered" spacing={4}>
            <List.Item>Press <b>Run first access</b> below. UNDM starts listening on the console.</List.Item>
            <List.Item><b>Then switch the modem off and on.</b> About 2½ minutes later it asks for a key for 3 seconds: UNDM
              presses Enter and answers its start-up questions. UNDM waits up to 10 minutes for that question.</List.Item>
            <List.Item>Wait: the modem starts again (2–3 minutes), UNDM logs in, sets the admin password and saves. The whole run
              takes up to about 15 minutes. Keep this window open.</List.Item>
          </List>
          <Notice kind="caution" compact>
            For a modem from the factory. One whose boot options have no auto-discovery is left alone: UNDM sends no key and changes nothing.
          </Notice>
          <TextInput label={`Type the device name to confirm: ${device.name}`} value={confirm} onChange={(e) => setConfirm(e.currentTarget.value)} />
          {run.isPending && (
            <Notice kind="status" compact title="Working on the console">
              Keep the cable connected and this window open.
              <Progress deviceId={device.id} />
            </Notice>
          )}
          <DialogError error={run.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Cancel</Button>
            <Button color="orange" disabled={confirm.trim() !== device.name} loading={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: (r) => { setResult(r); close(); } })}>Run first access</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

import {
  Badge, Button, Card, Checkbox, Code, CopyButton, Group, List, Modal, NumberInput, Select, SimpleGrid, Stack,
  Text, TextInput, Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconPlugConnected, IconRefresh, IconTerminal2 } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { Notice, type NoticeKind } from '../../components/Notice';
import { SafetyHint } from '../../components/SafetyHint';
import { useAction, useCredentialRefs, useLoginDefaults, usePolicy, useSerialPorts } from '../../hooks/queries';
import { paths } from '../../paths';
import { api } from '../../services/api';
import { downloadText } from '../../services/format';
import type { BootstrapPreview, BootstrapProfile, BootstrapResult, Device } from '../../types/api';
import { roleOf } from '../stage/roles';

const BAUD = ['9600', '19200', '38400', '57600', '115200'];
const STATUS: Record<BootstrapResult['status'], { kind: NoticeKind; title: string }> = {
  bootstrapped: { kind: 'success', title: 'Bootstrap complete' },
  already_configured: { kind: 'success', title: 'Already bootstrapped — nothing was changed' },
  refused: { kind: 'caution', title: 'Refused — the switch does not look factory default' },
  failed: { kind: 'error', title: 'Bootstrap failed' },
};

/** The console setup of an Aruba 2930F (D-025, D-057, D-095): its first address and login, after
 *  an optional erase. Shared by the console tool and Stage a system. */
export function ArubaBootstrap({ device, simulated, back }: {
  device: Device; simulated: boolean;
  /** Inside Stage a system: the way back to its step, offered once the setup is done. */
  back?: { label: string; onClick: () => void };
}) {
  const ports = useSerialPorts();
  const policy = usePolicy();
  const saved = device.bootstrap_profile;
  const [vlanId, setVlanId] = useState<number | string>(saved?.vlan_id ?? 222);
  const [vlanName, setVlanName] = useState(saved?.vlan_name ?? 'OOBM_VLAN');
  // Not saved yet: start from the bench cabling of its role in Stage a system.
  const role = roleOf(device);
  const [port, setPort] = useState(saved?.untagged_port ?? role?.consolePort ?? '');
  const [address, setAddress] = useState(saved?.address ?? (role?.consolePort ? `${role.address}/24` : '192.168.1.1/24'));
  const [serialPort, setSerialPort] = useState<string | null>(simulated ? 'SIMULATED' : null);
  const [baud, setBaud] = useState('9600');
  const [preview, setPreview] = useState<BootstrapPreview | null>(null);
  const [result, setResult] = useState<BootstrapResult | null>(null);
  const [confirm, setConfirm] = useState('');
  const [allowConfigured, setAllowConfigured] = useState(false);
  // Preconfigured switch (e.g. BH-DMZ units): erase its configuration first (D-057).
  const [erase, setErase] = useState(false);
  // "Login it has now": the 2930F default for all systems (D-105) until the person chooses.
  const defaults = useLoginDefaults();
  const [chosenLogin, setCurrentLogin] = useState<string | null | undefined>(undefined);
  const currentLogin = chosenLogin !== undefined ? chosenLogin
    : simulated ? null : defaults.data?.aruba?.current ?? null;
  // The name is read from the console by UNDM and confirmed by the person (D-095).
  const [seen, setSeen] = useState<{ state: string; hostname: string; message: string } | null>(null);
  const [eraseOk, setEraseOk] = useState(false);
  const hostname = seen?.state === 'configured' ? seen.hostname : '';
  const refs = useCredentialRefs(device.project_id);
  // After an erase the switch is set up as new with this device's own login: it must be one
  // with a password (the approved login), and not the login being erased.
  const ownLogin = refs.data?.find((r) => r.id === device.credential_ref_id);
  const loginName = (id: string | null) => refs.data?.find((r) => r.id === id)?.name;
  const ownProblem = !ownLogin ? 'This device has no login chosen.'
    : ownLogin.empty_password ? `Its login "${ownLogin.name}" has no password.`
      : ownLogin.id === currentLogin ? `Its login "${ownLogin.name}" is the login being erased.` : null;
  const [opened, { open, close }] = useDisclosure();

  const profile: BootstrapProfile = { vlan_id: Number(vlanId), vlan_name: vlanName.trim(), untagged_port: port.trim(), address: address.trim() };
  const complete = !!profile.vlan_id && !!profile.vlan_name && !!profile.untagged_port && /^\d+\.\d+\.\d+\.\d+\/\d+$/.test(profile.address);
  const save = useAction(() => api.updateDevice(device.id, { bootstrap_profile: profile }), 'Bootstrap settings saved');
  const chooseOwn = useAction((ref: string | null) => api.updateDevice(device.id, { credential_ref_id: ref }), 'Approved login chosen');
  const loginOptions = (refs.data ?? []).map((r) => ({ value: r.id, label: r.name }));
  const doPreview = useAction(() => api.bootstrapPreview(device.id, profile));
  const run = useAction(() => api.consoleBootstrap(device.id, {
    serial_port: serialPort!, baudrate: Number(baud), profile, confirm_device_name: confirm,
    allow_configured: allowConfigured && !erase,
    ...(currentLogin ? { current_credential_ref_id: currentLogin } : {}),
    ...(erase ? { erase_existing: true, confirm_hostname: hostname.trim() } : {}),
  }), undefined, { errorInDialog: true });
  const identify = useAction(() => api.consoleIdentify(device.id, {
    serial_port: serialPort!, baudrate: Number(baud), current_credential_ref_id: currentLogin,
  }), undefined, { errorInDialog: true });
  const blocked = !simulated && policy.data && !policy.data.enable_real_device_writes;
  const portOptions = (ports.data ?? [])
    .filter((p) => (simulated ? p.port === 'SIMULATED' : p.port !== 'SIMULATED'))
    .map((p) => ({ value: p.port, label: p.description ? `${p.port} — ${p.description}` : p.port }));

  return (
    <Stack>
      <Card withBorder>
        <Title order={2} size="h5" mb="xs">1 · Management settings for this switch</Title>
        <Text size="sm" c="dimmed" mb="sm">
          An out-of-band management VLAN with one untagged port and an address. Saved per device, so each switch keeps its own
          port and (temporary) address.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <NumberInput label="VLAN ID" min={2} max={4094} value={vlanId} onChange={setVlanId} />
          <TextInput label="VLAN name" value={vlanName} onChange={(e) => setVlanName(e.currentTarget.value)} />
          <TextInput label="Untagged port" placeholder="e.g. 2" value={port} onChange={(e) => setPort(e.currentTarget.value)}
            description={role?.consolePort ? `Stage a system: port ${role.consolePort} for this switch` : undefined} />
          <TextInput label="Address / prefix" placeholder="192.168.1.1/24" value={address} onChange={(e) => setAddress(e.currentTarget.value)} />
        </SimpleGrid>
        {role?.consolePort && port.trim() && port.trim() !== role.consolePort && (
          <Notice kind="caution" compact>
            The bench cabling uses port {role.consolePort} for this switch ({role.title}). Port {port.trim()} is used only if you cable it so.
          </Notice>
        )}
        <Group mt="sm">
          <Button variant="default" disabled={!complete} loading={save.isPending} onClick={() => save.mutate()}>Save settings</Button>
          <Button variant="light" disabled={!complete} loading={doPreview.isPending}
            onClick={() => doPreview.mutate(undefined, { onSuccess: setPreview })}>Preview commands</Button>
        </Group>
        {preview && (
          <Stack gap="xs" mt="md">
            <Text size="sm" fw={600}>Commands that will be typed on the console</Text>
            <Code block>{preview.commands.join('\n')}</Code>
            <List size="sm" spacing={2}>{preview.notes.map((n) => <List.Item key={n}>{n}</List.Item>)}</List>
          </Stack>
        )}
      </Card>

      <Card withBorder>
        <Title order={2} size="h5" mb="xs">2 · Console connection</Title>
        <Group align="flex-end">
          <Select label="Serial port" w="100%" maw={380} placeholder={portOptions.length ? 'Choose the console cable’s port' : 'No serial ports found'}
            data={portOptions} value={serialPort} onChange={setSerialPort} />
          <Select label="Speed (baud)" w={130} data={BAUD} value={baud} onChange={(v) => setBaud(v ?? '9600')} disabled={simulated} allowDeselect={false} />
          <Button variant="default" leftSection={<IconRefresh size={14} />} onClick={() => void ports.refetch()} loading={ports.isFetching}>Refresh ports</Button>
        </Group>
        {!simulated && (
          <Text size="xs" c="dimmed" mt="xs">
            Connect the console cable to the switch, then refresh. Close PuTTY or any other terminal program first: only one
            program can use a COM port. Settings used: 8 data bits, no parity, 1 stop bit.
          </Text>
        )}
        <Group mt="md">
          <Button leftSection={<IconTerminal2 size={16} />} disabled={!complete || !serialPort || !!blocked}
            onClick={() => { setConfirm(''); open(); }}>Run console bootstrap…</Button>
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
            {result.erased && <Badge variant="light" color="orange">erased “{result.erased}” first</Badge>}
            {result.no_password && <Badge variant="light" color="yellow">no manager password</Badge>}
            {result.password_set && <Badge variant="light" color="teal">manager password set</Badge>}
            <Badge variant="light" color={result.verified ? 'teal' : 'gray'}>{result.verified ? 'read back and verified' : 'not verified'}</Badge>
            <Badge variant="light" color={result.saved ? 'teal' : 'gray'}>{result.saved ? 'saved (write memory)' : 'not saved'}</Badge>
            {result.network_reachable !== null && <Badge variant="light" color={result.network_reachable ? 'teal' : 'yellow'}>
              {result.network_reachable ? 'reachable over the network' : 'not reachable over the network yet'}</Badge>}
          </Group>
          <Text size="sm" fw={600}>Console transcript</Text>
          <Code block mah={360} style={{ overflow: 'auto', fontSize: 11 }}>{result.transcript}</Code>
          <Group mt="xs">
            <CopyButton value={result.sanitized_transcript}>{({ copied, copy }) => <Button size="xs" variant="default" onClick={copy}>{copied ? 'Copied' : 'Copy sanitized transcript'}</Button>}</CopyButton>
            <Button size="xs" variant="default" leftSection={<IconDownload size={14} />}
              onClick={() => downloadText('undm-console-bootstrap-sanitized.txt', result.sanitized_transcript)}>Download sanitized transcript</Button>
            {(result.status === 'bootstrapped' || result.status === 'already_configured') && (
              back
                ? <Button size="xs" onClick={back.onClick}>{back.label}</Button>
                : <Button size="xs" component={Link} to={paths.device(device.id)} leftSection={<IconPlugConnected size={14} />}>Continue on the device page</Button>
            )}
          </Group>
        </Card>
      )}

      <Modal opened={opened} onClose={close} title="Run console bootstrap">
        <Stack>
          <Text size="sm">
            UNDM will log in on <b>{serialPort}</b>, check that the switch is factory default, type the previewed commands, read the
            configuration back and save it. {simulated ? 'This is a simulated console; no real device is involved.'
              : 'Make sure the console cable is plugged into the right switch.'}
          </Text>
          <Card withBorder padding="sm">
            <Stack gap={6}>
              <Text size="sm" fw={600}>Logins</Text>
              <Select size="xs" label="Login it has now" clearable data={loginOptions} value={currentLogin}
                description="Factory or preconfigured login. Leave empty for a new switch. UNDM uses it if the approved login is refused, and for an erase."
                placeholder={refs.data?.length ? 'Choose its current login' : "Add it on the system's Logins tab"}
                onChange={(v) => { setCurrentLogin(v); setSeen(null); setEraseOk(false); }} />
              <Select size="xs" label="Approved login (its login after the setup)" data={loginOptions} value={device.credential_ref_id}
                description="Set on a new or erased switch; saved as this device's login."
                placeholder="Choose the approved login" onChange={(v) => chooseOwn.mutate(v)} />
              {ownProblem && <Notice kind="error" compact>{ownProblem} Choose the approved login here.</Notice>}
            </Stack>
          </Card>
          <Checkbox label="This switch is preconfigured (it has a manager password that is not the approved one): erase its configuration first"
            checked={erase} onChange={(e) => setErase(e.currentTarget.checked)} />
          {erase && (
            <Stack gap={6}>
              <Notice kind="caution" compact title="The erase cannot be undone"
                details={<>UNDM logs in with the switch's <b>current login</b>, checks again that it is the switch whose name it read, saves a
                  copy of its configuration in the transcript, runs <code>erase startup-config</code> and confirms it, waits for the
                  restart (up to 7 minutes), then sets the switch up as new with this device's login and bootstraps it. Any question
                  UNDM does not recognise stops it with the switch's text.</>}>
                Its configuration is erased, then it is set up as a new switch.
              </Notice>
                <Text size="xs">Erased with <b>{loginName(currentLogin) ?? 'the login it has now (choose it above)'}</b>, then set up
                  with <b>{ownLogin?.name ?? 'the approved login (choose it above)'}</b>. If the switch keeps its password after
                  the erase, UNDM carries on with the login it has now.</Text>
                <Group gap="xs">
                  <Button size="xs" variant="light" disabled={!currentLogin} loading={identify.isPending}
                    onClick={() => { setEraseOk(false); identify.mutate(undefined, { onSuccess: setSeen }); }}>Read its name from the console</Button>
                  <Text size="xs" c="dimmed">Logs in and reads the name. Changes nothing.</Text>
                </Group>
                <DialogError error={identify.error} />
                {seen && seen.state === 'configured' && (
                  <Checkbox checked={eraseOk} onChange={(e) => setEraseOk(e.currentTarget.checked)}
                    label={<>The switch on this console is <b>{seen.hostname}</b>. Yes, erase {seen.hostname}.</>} />
                )}
                {seen && seen.state !== 'configured' && (
                  <Notice kind={seen.state === 'unknown' ? 'error' : 'settled'} compact>{seen.message}</Notice>
                )}
            </Stack>
          )}
          {!erase && <Checkbox label="The switch already has configuration — bootstrap it anyway" checked={allowConfigured}
            onChange={(e) => setAllowConfigured(e.currentTarget.checked)} />}
          <TextInput label={`Type the device name to confirm: ${device.name}`} value={confirm} onChange={(e) => setConfirm(e.currentTarget.value)} />
          {run.isPending && (
            <Notice kind="status" compact title="Working on the console">{erase
              ? 'Erasing, then the switch restarts (1–2 minutes), then UNDM presses Enter every 10 seconds until it answers and bootstraps it. This can take up to 8 minutes. Keep the console cable connected and this window open.'
              : 'Keep the cable connected.'}</Notice>
          )}
          <DialogError error={run.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Cancel</Button>
            <Button color={erase ? 'red' : 'orange'} disabled={confirm.trim() !== device.name || (erase && (!currentLogin || !hostname || !eraseOk || !!ownProblem))}
              loading={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: (r) => { setResult(r); close(); } })}>{erase ? 'Erase and bootstrap' : 'Run bootstrap'}</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}


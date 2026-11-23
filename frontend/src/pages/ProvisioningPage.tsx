import {
  Alert, Badge, Button, Card, Checkbox, Code, CopyButton, Group, List, Modal, NumberInput, Select, SimpleGrid, Stack,
  Text, TextInput, Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconAlertTriangle, IconCircleCheck, IconDownload, IconPlugConnected, IconRefresh, IconTerminal2 } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';

import { EnvironmentBadge } from '../components/Badges';
import { NotImplemented } from '../components/NotImplemented';
import { PageHeader, QueryState } from '../components/Page';
import { useAction, useAllDevices, useCredentialRefs, useDrivers, usePolicy, useProjects, useSerialPorts } from '../hooks/queries';
import { api } from '../services/api';
import { downloadText } from '../services/format';
import type { BootstrapPreview, BootstrapProfile, BootstrapResult, Device } from '../types/api';

const CONSOLE_PLATFORMS = new Set(['aos_switch']);
const BAUD = ['9600', '19200', '38400', '57600', '115200'];
const STATUS: Record<BootstrapResult['status'], { color: string; title: string }> = {
  bootstrapped: { color: 'teal', title: 'Bootstrap complete' },
  already_configured: { color: 'teal', title: 'Already bootstrapped — nothing was changed' },
  refused: { color: 'orange', title: 'Refused — the switch does not look factory default' },
  failed: { color: 'red', title: 'Bootstrap failed' },
};

function Bootstrap({ device, simulated }: { device: Device; simulated: boolean }) {
  const ports = useSerialPorts();
  const policy = usePolicy();
  const saved = device.bootstrap_profile;
  const [vlanId, setVlanId] = useState<number | string>(saved?.vlan_id ?? 222);
  const [vlanName, setVlanName] = useState(saved?.vlan_name ?? 'OOBM_VLAN');
  const [port, setPort] = useState(saved?.untagged_port ?? '');
  const [address, setAddress] = useState(saved?.address ?? '192.168.1.1/24');
  const [serialPort, setSerialPort] = useState<string | null>(simulated ? 'SIMULATED' : null);
  const [baud, setBaud] = useState('9600');
  const [preview, setPreview] = useState<BootstrapPreview | null>(null);
  const [result, setResult] = useState<BootstrapResult | null>(null);
  const [confirm, setConfirm] = useState('');
  const [allowConfigured, setAllowConfigured] = useState(false);
  // Preconfigured switch (e.g. BH-DMZ units): erase its configuration first (D-057).
  const [erase, setErase] = useState(false);
  const [currentLogin, setCurrentLogin] = useState<string | null>(null);
  const [hostname, setHostname] = useState('');
  const refs = useCredentialRefs(device.project_id);
  const [opened, { open, close }] = useDisclosure();

  const profile: BootstrapProfile = { vlan_id: Number(vlanId), vlan_name: vlanName.trim(), untagged_port: port.trim(), address: address.trim() };
  const complete = !!profile.vlan_id && !!profile.vlan_name && !!profile.untagged_port && /^\d+\.\d+\.\d+\.\d+\/\d+$/.test(profile.address);
  const save = useAction(() => api.updateDevice(device.id, { bootstrap_profile: profile }), 'Bootstrap settings saved');
  const doPreview = useAction(() => api.bootstrapPreview(device.id, profile));
  const run = useAction(() => api.consoleBootstrap(device.id, {
    serial_port: serialPort!, baudrate: Number(baud), profile, confirm_device_name: confirm,
    allow_configured: allowConfigured && !erase,
    ...(erase ? { erase_existing: true, current_credential_ref_id: currentLogin, confirm_hostname: hostname.trim() } : {}),
  }));
  const blocked = !simulated && policy.data && !policy.data.enable_real_device_writes;
  const portOptions = (ports.data ?? [])
    .filter((p) => (simulated ? p.port === 'SIMULATED' : p.port !== 'SIMULATED'))
    .map((p) => ({ value: p.port, label: p.description ? `${p.port} — ${p.description}` : p.port }));

  return (
    <Stack>
      <Card withBorder>
        <Title order={5} mb="xs">1 · Management settings for this switch</Title>
        <Text size="sm" c="dimmed" mb="sm">
          An out-of-band management VLAN with one untagged port and an address. Saved per device, so each switch keeps its own
          port and (temporary) address.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <NumberInput label="VLAN ID" min={2} max={4094} value={vlanId} onChange={setVlanId} />
          <TextInput label="VLAN name" value={vlanName} onChange={(e) => setVlanName(e.currentTarget.value)} />
          <TextInput label="Untagged port" placeholder="e.g. 2" value={port} onChange={(e) => setPort(e.currentTarget.value)} />
          <TextInput label="Address / prefix" placeholder="192.168.1.1/24" value={address} onChange={(e) => setAddress(e.currentTarget.value)} />
        </SimpleGrid>
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
        <Title order={5} mb="xs">2 · Console connection</Title>
        <Group align="flex-end">
          <Select label="Serial port" w={380} placeholder={portOptions.length ? 'Choose the console cable’s port' : 'No serial ports found'}
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
        {blocked && (
          <Alert color="orange" mt="sm" icon={<IconAlertTriangle size={16} />}>
            Changes to real devices are switched off on this server. Add <code>UNDM_ENABLE_REAL_DEVICE_WRITES=true</code> to
            <code> backend\.env</code> and restart the backend to run a console bootstrap. Preview still works.
          </Alert>
        )}
        <Group mt="md">
          <Button leftSection={<IconTerminal2 size={16} />} disabled={!complete || !serialPort || !!blocked}
            onClick={() => { setConfirm(''); open(); }}>Run console bootstrap…</Button>
        </Group>
      </Card>

      {result && (
        <Card withBorder>
          <Alert color={STATUS[result.status].color} title={STATUS[result.status].title} mb="sm"
            icon={result.status === 'failed' || result.status === 'refused' ? <IconAlertTriangle size={18} /> : <IconCircleCheck size={18} />}>
            <Text size="sm">{result.message}</Text>
            {result.findings.length > 0 && <List size="sm" mt={4}>{result.findings.map((f) => <List.Item key={f}>{f}</List.Item>)}</List>}
            {result.network_hint && <Text size="sm" mt={6}>{result.network_hint}</Text>}
          </Alert>
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
              <Button size="xs" component={Link} to={`/devices/${device.id}`} leftSection={<IconPlugConnected size={14} />}>Continue on the device page</Button>
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
          <Checkbox label="This switch is preconfigured (it has a manager password that is not the approved one): erase its configuration first"
            checked={erase} onChange={(e) => setErase(e.currentTarget.checked)} />
          {erase && (
            <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />} p="xs">
              <Text size="xs" mb={6}>
                UNDM logs in with the switch's <b>current login</b>, checks that its hostname is the one you type, saves a copy of its
                configuration in the transcript, runs <code>erase startup-config</code> and confirms it, waits for the restart (up to
                7 minutes), then sets the switch up as new with this device's login and bootstraps it. The erase cannot be undone.
                Any question UNDM does not recognise stops it with the switch's text.
              </Text>
              <Stack gap={6}>
                <Select size="xs" label="Its current login" placeholder={refs.data?.length ? 'Choose the preconfigured login' : 'Add it on the project Credentials tab'}
                  data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))} value={currentLogin} onChange={setCurrentLogin} />
                <TextInput size="xs" label="Type its current hostname"
                  description="The name in its console prompt, before > or # (e.g. for a prompt 'sw-name#' type sw-name). Not the username."
                  placeholder="as shown in the console prompt"
                  value={hostname} onChange={(e) => setHostname(e.currentTarget.value)} />
              </Stack>
            </Alert>
          )}
          {!erase && <Checkbox label="The switch already has configuration — bootstrap it anyway" checked={allowConfigured}
            onChange={(e) => setAllowConfigured(e.currentTarget.checked)} />}
          <TextInput label={`Type the device name to confirm: ${device.name}`} value={confirm} onChange={(e) => setConfirm(e.currentTarget.value)} />
          {run.isPending && (
            <Alert color="yellow" variant="light" p="xs">
              <Text size="xs">{erase
                ? 'Working on the console: erasing, then the switch restarts (1–2 minutes), then UNDM presses Enter every 10 seconds until it answers and bootstraps it. This can take up to 8 minutes. Keep the console cable connected and this window open.'
                : 'Working on the console… keep the cable connected.'}</Text>
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Cancel</Button>
            <Button color={erase ? 'red' : 'orange'} disabled={confirm.trim() !== device.name || (erase && (!currentLogin || !hostname.trim()))}
              loading={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: (r) => { setResult(r); close(); } })}>{erase ? 'Erase and bootstrap' : 'Run bootstrap'}</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

export function ProvisioningPage() {
  const [params, setParams] = useSearchParams();
  const devices = useAllDevices();
  const drivers = useDrivers();
  const projects = useProjects();
  const platform = new Map((drivers.data ?? []).map((d) => [d.driver_id, d]));
  const eligible = (devices.data ?? []).filter((d) => CONSOLE_PLATFORMS.has(platform.get(d.driver_id)?.platform ?? ''));
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const deviceId = params.get('device');
  const device = eligible.find((d) => d.id === deviceId);

  return (
    <>
      <PageHeader title="Provisioning Center"
        description="Give a factory-default device its first management address through the console cable, so it can be reached over the network." />
      <QueryState isLoading={devices.isLoading || drivers.isLoading} error={devices.error ?? drivers.error} />
      <Stack>
        <Card withBorder>
          <Select label="Device" w={520} searchable
            placeholder={eligible.length ? 'Choose a switch' : 'No devices with a console bootstrap procedure yet'}
            data={eligible.map((d) => ({ value: d.id, label: `${d.name} — ${d.manufacturer} ${d.model} (${names.get(d.project_id) ?? ''})` }))}
            value={device?.id ?? null} onChange={(v) => setParams(v ? { device: v } : {})} />
          {device && <Group gap="xs" mt="xs"><EnvironmentBadge env={device.environment} /><Text size="sm">driver <code>{device.driver_id}</code> · provisioning status: {device.provisioning_status.replaceAll('_', ' ')}</Text></Group>}
          <Text size="xs" c="dimmed" mt="xs">
            Console bootstrap is available for ArubaOS-Switch (e.g. Aruba 2930F). It has not been validated on hardware yet:
            run it first on a spare switch on an isolated bench.
          </Text>
        </Card>
        {device && <Bootstrap key={device.id} device={device} simulated={platform.get(device.driver_id)?.simulated ?? true} />}
        <NotImplemented title="Zero-touch and network-based provisioning" phase="later phases"
          note="Only the console bootstrap above is available today." planned={[
          'FortiGate and Black Box first-login handling at their factory-default addresses',
          'DHCP-based bootstrap for switches that request an address at factory default (to be verified on a spare unit)',
          'A staging run that takes all devices of a system through bootstrap, firmware and configuration in one go',
        ]} />
      </Stack>
    </>
  );
}

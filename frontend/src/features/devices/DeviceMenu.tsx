import { ActionIcon, Button, FileInput, Group, Menu, Modal, Stack, Table, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconActivity, IconCertificate, IconClipboard, IconDots, IconExternalLink, IconFileText, IconInfoCircle, IconPlugConnected,
  IconPower, IconRocket, IconTerminal, IconTerminal2, IconTrash, IconWorld, IconEdit } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { Notice } from '../../components/Notice';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import { factLabel, MAIN_FACTS } from '../../services/labels';
import { showError, showSuccess } from '../../services/notify';
import type { Device } from '../../types/api';
import { paths } from '../../paths';

const can = (d: Device, c: string) => d.capabilities.includes(c);

/**
 * One menu for a device, everywhere it is listed (D-099): the "⋯" button, and a right-click
 * on its row (`openDeviceMenu`). Read-only items run at once; a restart is a plan
 * (preview, approval, run) like every other change.
 */
export function DeviceMenu({ device, onDelete, onEdit, size = 'md' }: {
  device: Device; onDelete?: () => void; onEdit?: () => void; size?: 'md' | 'lg';
}) {
  const navigate = useNavigate();
  const real = device.environment !== 'simulated';
  const address = device.management_address;
  const [info, setInfo] = useState<Device | null>(null);
  const [restartOpen, restart] = useDisclosure();
  const [licenseOpen, license] = useDisclosure();
  const [licenseFile, setLicenseFile] = useState<File | null>(null);
  const waiting = useRef<number | null>(null);
  useEffect(() => () => { if (waiting.current) window.clearInterval(waiting.current); }, []);

  const run = useAction(({ op }: { op: string }) => api.runOperation(device.id, op),
    (r) => (r.status === 'success' ? `${device.name}: ${r.message || 'done'}` : `${device.name}: ${r.message}`));
  const check = useAction(async () => {
    const r = await api.runOperation(device.id, 'get_facts');
    if (r.status !== 'success') throw new Error(r.message);
    return api.device(device.id);
  }, undefined);
  const ssh = useAction(() => api.openSsh(device.id), () => `SSH window opened for ${device.name}: type the password there`);
  // Reached over its console only (the modem): a terminal on its console port instead (D-118).
  const consoleOnly = can(device, 'supports_serial_console') && !can(device, 'supports_ssh');
  const terminal = useAction(() => api.openConsole(device.id), (r) => `Console window opened on ${r.console_port}`
    + (r.program === 'putty' ? ' (PuTTY)' : ' (close it with Ctrl+])') + ': close it before UNDM uses this port again');
  const makeRestart = useAction(() => api.restartPlan(device.id), undefined, { errorInDialog: true });
  const makeLicense = useAction(async () => {
    const stored = await api.uploadLicense(device.id, licenseFile!);
    return api.licensePlan(device.id, stored.id);
  }, undefined, { errorInDialog: true });

  const waitUntilAnswers = () => {
    if (waiting.current) window.clearInterval(waiting.current);
    let tries = 0;
    showSuccess(`Watching ${device.name}: you will be told when it answers (up to 10 minutes)`);
    waiting.current = window.setInterval(() => {
      tries += 1;
      void api.reachability(device.project_id).then((rs) => {
        const me = rs.find((r) => r.device_id === device.id);
        if (me?.state === 'answers' || me?.state === 'simulated') {
          showSuccess(`${device.name} answers at ${me.address}`);
          window.clearInterval(waiting.current!); waiting.current = null;
        } else if (tries >= 60) {
          showError(`${device.name} did not answer within 10 minutes`);
          window.clearInterval(waiting.current!); waiting.current = null;
        }
      }).catch(() => undefined);
    }, 10_000);
  };

  return (
    <>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target><ActionIcon variant={size === 'lg' ? 'default' : 'subtle'} size={size === 'lg' ? 'lg' : 'md'}
          aria-label={`Actions for ${device.name}`} data-device-menu=""><IconDots size={size === 'lg' ? 18 : 16} /></ActionIcon></Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>{device.name}</Menu.Label>
          {real && !consoleOnly && <Menu.Item leftSection={<IconTerminal size={14} />} onClick={() => ssh.mutate(undefined)}>Open SSH window</Menu.Item>}
          {real && consoleOnly && <Menu.Item leftSection={<IconTerminal size={14} />} onClick={() => terminal.mutate(undefined)}>Open console window</Menu.Item>}
          {real && address && <Menu.Item leftSection={<IconWorld size={14} />} component="a" href={`https://${address}`} target="_blank"
            rel="noreferrer" rightSection={<IconExternalLink size={12} />}>Open web page</Menu.Item>}
          {address && <Menu.Item leftSection={<IconClipboard size={14} />}
            onClick={() => void navigator.clipboard?.writeText(address).then(() => showSuccess(`Copied ${address}`))}>Copy address</Menu.Item>}
          <Menu.Divider />
          <Menu.Item leftSection={<IconInfoCircle size={14} />} onClick={() => check.mutate(undefined, { onSuccess: setInfo })}>Check information</Menu.Item>
          <Menu.Item leftSection={<IconPlugConnected size={14} />} onClick={() => run.mutate({ op: 'check_reachability' })}>Test connection</Menu.Item>
          {!consoleOnly && <Menu.Item leftSection={<IconActivity size={14} />} onClick={waitUntilAnswers}>Wait until it answers</Menu.Item>}
          <Menu.Item leftSection={<IconFileText size={14} />} onClick={() => run.mutate({ op: 'backup_configuration' })}>Back up now</Menu.Item>
          <Menu.Item component={Link} to={paths.device(device.id, 'files')} leftSection={<IconFileText size={14} />}>Files and compare</Menu.Item>
          <Menu.Item component={Link} to={paths.device(device.id, 'log')} leftSection={<IconActivity size={14} />}>Device log</Menu.Item>
          <Menu.Label>Changes the device (approved plan)</Menu.Label>
          {can(device, 'supports_restart') && <Menu.Item leftSection={<IconPower size={14} />} onClick={restart.open}>Restart…</Menu.Item>}
          {can(device, 'supports_license_file') && <Menu.Item leftSection={<IconCertificate size={14} />} onClick={license.open}>Load license…</Menu.Item>}
          {(device.driver_id.includes('aos_switch') || consoleOnly) && <Menu.Item component={Link} to={paths.console(device.id)}
            leftSection={<IconTerminal2 size={14} />}>Console setup</Menu.Item>}
          <Menu.Item leftSection={<IconRocket size={14} />} onClick={() => void navigate(paths.planNew({ system: device.project_id, devices: device.id }))}>Make a plan…</Menu.Item>
          {onEdit && <><Menu.Divider />
            <Menu.Item leftSection={<IconEdit size={14} />} disabled={!!device.locked_by_deployment_id} onClick={onEdit}>Edit device…</Menu.Item></>}
          {onDelete && <><Menu.Divider />
            <Menu.Item color="red" leftSection={<IconTrash size={14} />} disabled={!!device.locked_by_deployment_id} onClick={onDelete}>Delete…</Menu.Item></>}
        </Menu.Dropdown>
      </Menu>

      <Modal opened={!!info} onClose={() => setInfo(null)} title={`Information · ${device.name}`}>
        {info && <DeviceInfo device={info} />}
      </Modal>

      <Modal opened={licenseOpen} onClose={license.close} title={`Load a license on ${device.name}`}>
        <Stack>
          <Text size="sm">Choose the license file the project lead sent. UNDM keeps it for this device (never shown), makes a plan
            that loads it, and opens the plan: check it, approve and run. The unit fetches the file from this PC and restarts with
            it; UNDM waits until it answers again.</Text>
          <FileInput label="License file" placeholder="Choose the .lic file" value={licenseFile} onChange={setLicenseFile} clearable />
          {real && <Notice kind="caution" compact>Experimental: this way of loading a license has not been run on a FortiGate yet. Afterwards,
            check the license status on its web page (System → FortiGuard).</Notice>}
          <DialogError error={makeLicense.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={license.close} data-autofocus>Cancel</Button>
            <Button disabled={!licenseFile} loading={makeLicense.isPending} leftSection={<IconCertificate size={16} />}
              onClick={() => makeLicense.mutate(undefined, { onSuccess: (p) => { license.close(); setLicenseFile(null); void navigate(paths.plan(p.id)); } })}>
              Make the license plan</Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={restartOpen} onClose={restart.close} title={`Restart ${device.name}`}>
        <Stack>
          <Text size="sm">UNDM makes a plan that restarts the device. You see what it will send, approve it, then run it; UNDM waits
            until the device answers again (same serial number) and records it all.</Text>
          <Notice kind="caution" compact>Changes that were not saved on the device are lost: it starts with its saved configuration.
</Notice>
          <DialogError error={makeRestart.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={restart.close} data-autofocus>Cancel</Button>
            <Button color="orange" loading={makeRestart.isPending} leftSection={<IconPower size={16} />}
              onClick={() => makeRestart.mutate(undefined, { onSuccess: (p) => { restart.close(); void navigate(paths.plan(p.id)); } })}>
              Make the restart plan</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

/** What UNDM last read from the device, in a few rows (Check information). */
export function DeviceInfo({ device }: { device: Device }) {
  const facts = { ...((device.observed_facts ?? {}) as Record<string, unknown>), ...(((device.observed_facts ?? {}) as { extra?: Record<string, unknown> }).extra ?? {}) };
  const rows = MAIN_FACTS.filter((k) => facts[k] !== undefined && facts[k] !== null && facts[k] !== '');
  const text = rows.map((k) => `${factLabel(k)}: ${String(facts[k])}`).join('\n');
  return (
    <Stack gap="xs">
      <Table verticalSpacing={4}>
        <Table.Tbody>
          {rows.map((k) => <Table.Tr key={k}><Table.Td c="dimmed">{factLabel(k)}</Table.Td><Table.Td ff="monospace">{String(facts[k])}</Table.Td></Table.Tr>)}
        </Table.Tbody>
      </Table>
      <Group justify="space-between">
        <Text size="xs" c="dimmed">Read {fmtDate(device.facts_retrieved_at)}</Text>
        <Button size="xs" variant="default" leftSection={<IconClipboard size={14} />}
          onClick={() => void navigator.clipboard?.writeText(text).then(() => showSuccess('Copied'))}>Copy</Button>
      </Group>
    </Stack>
  );
}

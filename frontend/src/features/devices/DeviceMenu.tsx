import { ActionIcon, Button, Group, Menu, Modal, Stack, Table, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconActivity, IconClipboard, IconDots, IconExternalLink, IconFileText, IconInfoCircle, IconPlugConnected,
  IconPower, IconRocket, IconTerminal, IconTerminal2, IconTrash, IconWorld,
} from '@tabler/icons-react';
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
import { temporaryAddress } from '../stage/roles';

const can = (d: Device, c: string) => d.capabilities.includes(c);

/**
 * One menu for a device, everywhere it is listed (D-099): the "⋯" button, and a right-click
 * on its row (`openDeviceMenu`). Read-only items run at once; a restart is a plan
 * (preview, approval, run) like every other change.
 */
export function DeviceMenu({ device, onDelete }: { device: Device; onDelete?: () => void }) {
  const navigate = useNavigate();
  const real = device.environment !== 'simulated';
  const address = temporaryAddress(device) || device.management_address;
  const [info, setInfo] = useState<Device | null>(null);
  const [restartOpen, restart] = useDisclosure();
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
  const makeRestart = useAction(() => api.restartPlan(device.id), undefined, { errorInDialog: true });

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
        <Menu.Target><ActionIcon variant="subtle" aria-label={`Actions for ${device.name}`} data-device-menu=""><IconDots size={16} /></ActionIcon></Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>{device.name}</Menu.Label>
          {real && <Menu.Item leftSection={<IconTerminal size={14} />} onClick={() => ssh.mutate(undefined)}>Open SSH window</Menu.Item>}
          {real && address && <Menu.Item leftSection={<IconWorld size={14} />} component="a" href={`https://${address}`} target="_blank"
            rel="noreferrer" rightSection={<IconExternalLink size={12} />}>Open web page</Menu.Item>}
          {address && <Menu.Item leftSection={<IconClipboard size={14} />}
            onClick={() => void navigator.clipboard?.writeText(address).then(() => showSuccess(`Copied ${address}`))}>Copy address</Menu.Item>}
          <Menu.Divider />
          <Menu.Item leftSection={<IconInfoCircle size={14} />} onClick={() => check.mutate(undefined, { onSuccess: setInfo })}>Check information</Menu.Item>
          <Menu.Item leftSection={<IconPlugConnected size={14} />} onClick={() => run.mutate({ op: 'check_reachability' })}>Test connection</Menu.Item>
          <Menu.Item leftSection={<IconActivity size={14} />} onClick={waitUntilAnswers}>Wait until it answers</Menu.Item>
          <Menu.Item leftSection={<IconFileText size={14} />} onClick={() => run.mutate({ op: 'backup_configuration' })}>Back up now</Menu.Item>
          <Menu.Item component={Link} to={`/devices/${device.id}?tab=configs`} leftSection={<IconFileText size={14} />}>Configurations and compare</Menu.Item>
          <Menu.Item component={Link} to={`/devices/${device.id}?tab=log`} leftSection={<IconActivity size={14} />}>Device log</Menu.Item>
          <Menu.Label>Changes the device (approved plan)</Menu.Label>
          {can(device, 'supports_restart') && <Menu.Item leftSection={<IconPower size={14} />} onClick={restart.open}>Restart…</Menu.Item>}
          {device.driver_id.includes('aos_switch') && <Menu.Item component={Link} to={`/provisioning?device=${device.id}`}
            leftSection={<IconTerminal2 size={14} />}>Console setup</Menu.Item>}
          <Menu.Item leftSection={<IconRocket size={14} />} onClick={() => void navigate(`/deployments?project=${device.project_id}&devices=${device.id}`)}>Make a plan…</Menu.Item>
          {onDelete && <><Menu.Divider />
            <Menu.Item color="red" leftSection={<IconTrash size={14} />} disabled={!!device.locked_by_deployment_id} onClick={onDelete}>Delete…</Menu.Item></>}
        </Menu.Dropdown>
      </Menu>

      <Modal opened={!!info} onClose={() => setInfo(null)} title={`Information · ${device.name}`}>
        {info && <DeviceInfo device={info} />}
      </Modal>

      <Modal opened={restartOpen} onClose={restart.close} title={`Restart ${device.name}`}>
        <Stack>
          <Text size="sm">UNDM makes a plan that restarts the device. You see what it will send, approve it, then run it; UNDM waits
            until the device answers again (same serial number) and records it all.</Text>
          <Notice kind="caution" compact>Changes that were not saved on the device are lost: it starts with its saved configuration.
            {temporaryAddress(device) ? ` It returns to ${device.management_address}.` : ''}</Notice>
          <DialogError error={makeRestart.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={restart.close}>Back</Button>
            <Button color="orange" loading={makeRestart.isPending} leftSection={<IconPower size={16} />}
              onClick={() => makeRestart.mutate(undefined, { onSuccess: (p) => { restart.close(); void navigate(`/deployments/${p.id}`); } })}>
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

/** Right-click on a row: open the menu of the "⋯" button in that row. */
export function openDeviceMenu(e: React.MouseEvent<HTMLElement>) {
  const button = e.currentTarget.querySelector<HTMLButtonElement>('[data-device-menu]');
  if (!button) return;
  e.preventDefault();
  // The menu closes on a press outside it: open it once the right button is released
  // (on Windows the right-click event comes after the release, elsewhere before it).
  const open = () => window.setTimeout(() => button.click(), 0);
  if (e.buttons & 2) window.addEventListener('mouseup', open, { once: true });
  else open();
}


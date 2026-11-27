import { Button, Group, Modal, Select, Stack, Text } from '@mantine/core';
import { IconTerminal } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { LoadingLines } from '../../components/Page';
import { useAction, useSerialPorts } from '../../hooks/queries';
import { api } from '../../services/api';
import type { Device } from '../../types/api';
import { CONSOLE_SPEEDS } from './consoleSpeeds';

/**
 * A console window on this PC for any real device (D-126): PuTTY, else pySerial's terminal,
 * on the COM port its console cable is on. UNDM types nothing in it. The port and speed
 * chosen are kept for the device.
 */
export function ConsoleWindowDialog({ device, opened, onClose }: { device: Device; opened: boolean; onClose: () => void }) {
  const settings = useQuery({ queryKey: ['console-settings', device.id], queryFn: () => api.consoleSettings(device.id), enabled: opened });
  return (
    <Modal opened={opened} onClose={onClose} title={`Console window · ${device.name}`}>
      {settings.isLoading && <LoadingLines lines={3} />}
      {settings.data && <ConsoleForm key={device.id} device={device} port={settings.data.console_port}
        speed={settings.data.console_speed} source={settings.data.source} onClose={onClose} />}
      {settings.error && <DialogError error={settings.error} />}
    </Modal>
  );
}

function ConsoleForm({ device, port, speed, source, onClose }: {
  device: Device; port: string | null; speed: number | null; source: string; onClose: () => void;
}) {
  const ports = useSerialPorts();
  const [chosenPort, setPort] = useState<string | null>(port);
  const [chosenSpeed, setSpeed] = useState<string | null>(speed ? String(speed) : null);
  const listed = (ports.data ?? []).filter((p) => p.port !== 'SIMULATED');
  const portData = [...new Set([...(port ? [port] : []), ...listed.map((p) => p.port)])].map((p) => ({
    value: p, label: listed.find((x) => x.port === p)?.description ? `${p} · ${listed.find((x) => x.port === p)!.description}` : p }));
  const open = useAction(() => api.openConsole(device.id, {
    console_port: chosenPort, console_speed: chosenSpeed && Number(chosenSpeed) !== speed ? Number(chosenSpeed) : null,
  }), (r) => `Console window opened on ${r.console_port} at ${r.console_speed}`
    + (r.program === 'putty' ? ' (PuTTY)' : ' (close it with Ctrl+])') + ': close it before UNDM uses this port again', { errorInDialog: true });
  return (
    <Stack>
      <Text size="sm">Connect the console cable to {device.name} and this PC. UNDM opens a terminal on that port; it types nothing in
        it. What you do there is not part of UNDM's plans or audit.</Text>
      <Select label="COM port of this PC" placeholder={ports.isLoading ? 'Looking for ports…' : 'Choose the port'} data={portData}
        value={chosenPort} onChange={setPort} searchable data-autofocus
        description={listed.length === 0 && !ports.isLoading ? 'No serial port found: plug in the USB console cable.' : undefined} />
      <Select label="Speed" data={CONSOLE_SPEEDS.map((s) => String(s))} value={chosenSpeed} onChange={setSpeed}
        placeholder="Choose its speed"
        description={speed && Number(chosenSpeed) === speed ? `${speed}: ${source}.` : speed ? `Its usual speed is ${speed} (${source}).`
          : 'UNDM has no documented speed for this model: choose the one it uses.'} />
      <Hint>8 data bits, no parity, 1 stop bit, no flow control. The window closes the port when you close it.</Hint>
      <DialogError error={open.error} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>Cancel</Button>
        <Button leftSection={<IconTerminal size={16} />} disabled={!chosenPort || !chosenSpeed} loading={open.isPending}
          onClick={() => open.mutate(undefined, { onSuccess: onClose })}>Open console window</Button>
      </Group>
    </Stack>
  );
}

import { Accordion, Button, Group, Modal, NumberInput, Select, SimpleGrid, Stack, TagsInput, Textarea, TextInput } from '@mantine/core';

import { useState } from 'react';

import { LoginSelect } from '../logins/LoginSelect';
import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useDrivers } from '../../hooks/queries';
import { api } from '../../services/api';
import { driverLabel } from '../../services/labels';
import type { Device, DeviceEnvironment, DeviceInput } from '../../types/api';
import { Notice } from '../../components/Notice';
import { Hint } from '../../components/Hint';

const PROTOCOLS = [
  { value: 'ssh', label: 'SSH' }, { value: 'https_api', label: 'HTTPS API' },
  { value: 'netconf', label: 'NETCONF' }, { value: 'serial', label: 'Serial console' },
];

export function EditDeviceModal({ device, opened, onClose }: { device: Device; opened: boolean; onClose: () => void }) {
  const drivers = useDrivers();
  const [f, setF] = useState<DeviceInput>({ ...device });
  const save = useAction((body: DeviceInput) => api.updateDevice(device.id, body), 'Device saved', { errorInDialog: true });
  const driver = drivers.data?.find((d) => d.driver_id === f.driver_id);
  const vendorDrivers = (drivers.data ?? []).filter((d) => d.vendor === device.manufacturer);
  const set = (k: keyof DeviceInput) => (e: { currentTarget: { value: string } }) => setF({ ...f, [k]: e.currentTarget.value });

  const chooseDriver = (id: string | null) => {
    const d = drivers.data?.find((x) => x.driver_id === id);
    if (!d) return;
    const environment: DeviceEnvironment = d.simulated ? 'simulated' : (f.environment === 'production' ? 'production' : 'lab');
    setF({ ...f, driver_id: d.driver_id, environment });
  };

  // Reached over its console only (the modem): its plans use this PC's console port (D-116).
  // The BBU is staged by hand in its portal: UNDM has no login for it (D-117).
  const guided = !!driver?.capabilities.includes('supports_guided_staging');
  const overConsole = !!driver && driver.capabilities.includes('supports_serial_console') && !driver.capabilities.includes('supports_ssh');
  const submit = () => {
    const body: DeviceInput = {
      name: f.name, role: f.role, model: f.model, hardware_revision: f.hardware_revision, os_family: f.os_family,
      firmware_version: f.firmware_version, management_address: f.management_address,
      management_protocol: f.management_protocol, management_port: f.management_port ?? null,
      ...(overConsole ? { console_port: f.console_port?.trim() || null } : {}),
      management_vrf: f.management_vrf, site: f.site, rack_location: f.rack_location, driver_id: f.driver_id,
      environment: f.environment, credential_ref_id: f.credential_ref_id ?? null, notes: f.notes, tags: f.tags,
    };
    save.mutate(body, { onSuccess: onClose });
  };

  return (
    <Modal opened={opened} onClose={onClose} title={`Edit ${device.name}`} size="xl">
      <Stack>
        {/* What people change (D-122); the rest is under "Advanced settings". */}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Device name" value={f.name ?? ''} onChange={set('name')} data-autofocus />
          <TextInput label="Address" placeholder="IP address or hostname" value={f.management_address ?? ''} onChange={set('management_address')} />
          {!guided && <LoginSelect projectId={device.project_id} label="Login" maw={9999} value={f.credential_ref_id ?? null}
            onChange={(v) => setF({ ...f, credential_ref_id: v })} />}
          {overConsole && !driver?.simulated && (
            <TextInput label="Console port" placeholder="e.g. COM3" value={f.console_port ?? ''} onChange={set('console_port')}
              description="The PC's serial port its console cable is on: its plans run over it. Its first access saves it." />
          )}
          <TextInput label="Site" value={f.site ?? ''} onChange={set('site')} />
          <TextInput label="Rack / physical location" value={f.rack_location ?? ''} onChange={set('rack_location')} />
        </SimpleGrid>
        <TagsInput label="Tags" value={f.tags ?? []} onChange={(tags) => setF({ ...f, tags })} />
        <Textarea label="Notes" autosize minRows={2} value={f.notes ?? ''} onChange={set('notes')} />
        {driver && f.os_family && driver.os_family !== f.os_family && (
          <Notice kind="error" title="Operating system mismatch">
            This device is recorded as <b>{f.os_family}</b> but connects as <b>{driver.os_family}</b>. Choose the one matching
            the device's operating system (an Aruba 2930F runs ArubaOS-Switch, not AOS-CX) under Advanced settings.
          </Notice>
        )}
        <Accordion variant="separated" defaultValue={driver && f.os_family && driver.os_family !== f.os_family ? 'advanced' : null}>
          <Accordion.Item value="advanced">
            <Accordion.Control>Advanced settings</Accordion.Control>
            <Accordion.Panel>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select label="Connects by" data={vendorDrivers.map((d) => ({ value: d.driver_id, label: `${driverLabel(d.driver_id, vendorDrivers)}${d.maturity === 'experimental' ? ' (experimental)' : ''}` }))}
                  value={f.driver_id ?? null} onChange={chooseDriver} allowDeselect={false} />
                <Select label="Environment" value={f.environment ?? 'simulated'} allowDeselect={false}
                  data={driver?.simulated ? [{ value: 'simulated', label: 'Simulated' }]
                    : [{ value: 'lab', label: 'Lab (isolated test equipment)' }, { value: 'production', label: 'Production' }]}
                  onChange={(v) => setF({ ...f, environment: (v ?? 'lab') as DeviceEnvironment })} />
                <Select label="Protocol" data={PROTOCOLS} value={f.management_protocol ?? 'ssh'} onChange={(v) => setF({ ...f, management_protocol: v ?? 'ssh' })} />
                <NumberInput label="Port" placeholder="default (22 for SSH)" min={1} max={65535} value={f.management_port ?? ''}
                  onChange={(v) => setF({ ...f, management_port: v === '' ? null : Number(v) })} />
                <TextInput label="Management VRF" value={f.management_vrf ?? ''} onChange={set('management_vrf')} />
                <TextInput label="Role" value={f.role ?? ''} onChange={set('role')} />
                <TextInput label="Model" value={f.model ?? ''} onChange={set('model')} />
                <TextInput label="Hardware revision" value={f.hardware_revision ?? ''} onChange={set('hardware_revision')} />
                <TextInput label="Operating system" value={f.os_family ?? ''} onChange={set('os_family')} />
                <TextInput label="Firmware version (declared)" value={f.firmware_version ?? ''} onChange={set('firmware_version')} />
              </SimpleGrid>
              {driver && !driver.simulated && (
                <Hint more={driver.notes.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{driver.notes.map((n) => <li key={n}>{n}</li>)}</ul> : undefined}>
                  Real device: {driver.description}. Its procedures are marked experimental until proven on the bench.
                </Hint>
              )}
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
        <DialogError error={save.error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={save.isPending} disabled={!f.name?.trim()}>Save</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

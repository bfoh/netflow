import { Button, Group, Modal, NumberInput, Select, SimpleGrid, Stack, TagsInput, Text, Textarea, TextInput } from '@mantine/core';

import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useCredentialRefs, useDrivers } from '../../hooks/queries';
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
  const refs = useCredentialRefs(device.project_id);
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

  const submit = () => {
    const body: DeviceInput = {
      name: f.name, role: f.role, model: f.model, hardware_revision: f.hardware_revision, os_family: f.os_family,
      firmware_version: f.firmware_version, management_address: f.management_address,
      management_protocol: f.management_protocol, management_port: f.management_port ?? null,
      management_vrf: f.management_vrf, site: f.site, rack_location: f.rack_location, driver_id: f.driver_id,
      environment: f.environment, credential_ref_id: f.credential_ref_id ?? null, notes: f.notes, tags: f.tags,
    };
    save.mutate(body, { onSuccess: onClose });
  };

  return (
    <Modal opened={opened} onClose={onClose} title={`Edit ${device.name}`} size="xl">
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Device name" value={f.name ?? ''} onChange={set('name')} />
          <TextInput label="Role" value={f.role ?? ''} onChange={set('role')} />
          <TextInput label="Model" value={f.model ?? ''} onChange={set('model')} />
          <TextInput label="Hardware revision" value={f.hardware_revision ?? ''} onChange={set('hardware_revision')} />
          <TextInput label="Operating system" value={f.os_family ?? ''} onChange={set('os_family')} />
          <TextInput label="Firmware version (declared)" value={f.firmware_version ?? ''} onChange={set('firmware_version')} />
        </SimpleGrid>
        <Text fw={600} mt="xs">Connection</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Connects by" data={vendorDrivers.map((d) => ({ value: d.driver_id, label: `${driverLabel(d.driver_id, vendorDrivers)}${d.maturity === 'experimental' ? ' (experimental)' : ''}` }))}
            value={f.driver_id ?? null} onChange={chooseDriver} allowDeselect={false} />
          <Select label="Environment" value={f.environment ?? 'simulated'} allowDeselect={false}
            data={driver?.simulated ? [{ value: 'simulated', label: 'Simulated' }]
              : [{ value: 'lab', label: 'Lab (isolated test equipment)' }, { value: 'production', label: 'Production' }]}
            onChange={(v) => setF({ ...f, environment: (v ?? 'lab') as DeviceEnvironment })} />
          <TextInput label="Address" placeholder="IP address or hostname" value={f.management_address ?? ''} onChange={set('management_address')} />
          <Select label="Protocol" data={PROTOCOLS} value={f.management_protocol ?? 'ssh'} onChange={(v) => setF({ ...f, management_protocol: v ?? 'ssh' })} />
          <NumberInput label="Port" placeholder="default (22 for SSH)" min={1} max={65535} value={f.management_port ?? ''}
            onChange={(v) => setF({ ...f, management_port: v === '' ? null : Number(v) })} />
          <TextInput label="Management VRF" value={f.management_vrf ?? ''} onChange={set('management_vrf')} />
          <Select label="Login" placeholder={refs.data?.length ? 'Choose a login' : 'Add one on the system\'s Logins tab'} clearable
            data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))} value={f.credential_ref_id ?? null}
            onChange={(v) => setF({ ...f, credential_ref_id: v })} />
        </SimpleGrid>
        {driver && f.os_family && driver.os_family !== f.os_family && (
          <Notice kind="error" title="Operating system mismatch">
            This device is recorded as <b>{f.os_family}</b> but connects as <b>{driver.os_family}</b>. Choose the one matching
            the device's operating system (an Aruba 2930F runs ArubaOS-Switch, not AOS-CX).
          </Notice>
        )}
        {driver && !driver.simulated && (
          <Hint more={driver.notes.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{driver.notes.map((n) => <li key={n}>{n}</li>)}</ul> : undefined}>
            Real device: {driver.description}. Its procedures are marked experimental until proven on the bench.
          </Hint>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Site" value={f.site ?? ''} onChange={set('site')} />
          <TextInput label="Rack / physical location" value={f.rack_location ?? ''} onChange={set('rack_location')} />
        </SimpleGrid>
        <TagsInput label="Tags" value={f.tags ?? []} onChange={(tags) => setF({ ...f, tags })} />
        <Textarea label="Notes" autosize minRows={2} value={f.notes ?? ''} onChange={set('notes')} />
        <DialogError error={save.error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={save.isPending} disabled={!f.name?.trim()}>Save</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

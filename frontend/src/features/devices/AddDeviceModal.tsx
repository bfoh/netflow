import { Button, Group, Modal, SegmentedControl, Select, SimpleGrid, Stack, Textarea, TextInput } from '@mantine/core';
import { IconFlask } from '@tabler/icons-react';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useCredentialRefs, useDeviceModels, useDrivers } from '../../hooks/queries';
import { api } from '../../services/api';
import { driverLabel } from '../../services/labels';
import { addressProblem } from '../../services/validation';
import { ROLES } from '../stage/roles';
import { Notice } from '../../components/Notice';
import { Hint } from '../../components/Hint';

const PROTOCOLS = [
  { value: 'ssh', label: 'SSH' }, { value: 'https_api', label: 'HTTPS API' },
  { value: 'netconf', label: 'NETCONF' }, { value: 'serial', label: 'Serial console' },
];

const empty = { name: '', role: '', management_address: '', management_protocol: 'ssh', site: '', rack_location: '', notes: '' };

export function AddDeviceModal({ projectId, opened, onClose }:
  { projectId: string; opened: boolean; onClose: () => void }) {
  const models = useDeviceModels();
  const drivers = useDrivers();
  const refs = useCredentialRefs(projectId);
  const [modelId, setModelId] = useState<string | null>(null);
  const [kind, setKind] = useState<'simulated' | 'real'>('simulated');
  const [credentialRef, setCredentialRef] = useState<string | null>(null);
  const [form, setForm] = useState(empty);
  const create = useAction((body: Parameters<typeof api.createDevice>[1]) => api.createDevice(projectId, body), 'Device added', { errorInDialog: true });
  const model = models.data?.find((m) => m.model_id === modelId);
  const isSim = (id: string) => drivers.data?.find((d) => d.driver_id === id)?.simulated ?? id.startsWith('mock.');
  const driverId = model?.drivers.find((id) => (kind === 'simulated' ? isSim(id) : !isSim(id)));
  const driver = drivers.data?.find((d) => d.driver_id === driverId);
  const set = (k: keyof typeof empty) => (e: { currentTarget: { value: string } }) =>
    setForm({ ...form, [k]: e.currentTarget.value });

  const submit = () => {
    if (!model || !driverId) return;
    create.mutate({
      ...form,
      manufacturer: model.manufacturer, product_family: model.product_family, model: model.model,
      category: model.category, os_family: model.os_family, driver_id: driverId,
      environment: kind === 'simulated' ? 'simulated' : 'lab',
      credential_ref_id: kind === 'real' ? credentialRef : null,
    }, { onSuccess: () => { setForm(empty); setModelId(null); setCredentialRef(null); onClose(); } });
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Add device" size="lg">
      <Stack>
        <Select
          label="Device model" required searchable placeholder="Choose the model"
          data={(models.data ?? []).map((m) => ({ value: m.model_id, label: `${m.manufacturer} ${m.model} (${m.category.replaceAll('_', ' ')})` }))}
          value={modelId} onChange={setModelId}
        />
        <SegmentedControl value={kind} onChange={(v) => setKind(v as 'simulated' | 'real')} data={[
          { value: 'simulated', label: 'Simulated device' }, { value: 'real', label: 'Real device on the bench' }]}
          aria-label="Simulated or real device" />
        {model && kind === 'simulated' && (
          <Hint icon={<IconFlask size={14} />}>{model.manufacturer} {model.model}: a simulated device that exists only inside UNDM.
            Use it to try plans safely.</Hint>
        )}
        {model && kind === 'real' && (
          driverId ? (
            <Notice kind="caution" compact title="Real device: use isolated test equipment"
              details={driver?.notes.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{driver.notes.map((n) => <li key={n}>{n}</li>)}</ul> : undefined}>
              UNDM connects over SSH ({driverLabel(driverId, drivers.data)}). Reading is always allowed; changes need an approved
              plan and Real-device changes on (Settings → Safety).
            </Notice>
          ) : <Hint>UNDM cannot reach a real {model.model} yet: only a simulated one can be added.</Hint>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Device name" required value={form.name} onChange={set('name')} />
          <TextInput label="Role" placeholder="e.g. LTE switch" value={form.role} onChange={set('role')} />
          <TextInput label="Address" description="The address UNDM reaches it at (factory address for a new unit)"
            placeholder={`e.g. ${ROLES.find((r) => r.model === model?.model)?.address ?? '192.0.2.1'}`}
            value={form.management_address} onChange={set('management_address')} error={addressProblem(form.management_address)} />
          <Select label="Connects by" data={PROTOCOLS} value={form.management_protocol}
            onChange={(v) => setForm({ ...form, management_protocol: v ?? 'ssh' })} />
          <TextInput label="Site" value={form.site} onChange={set('site')} />
          <TextInput label="Rack / physical location" value={form.rack_location} onChange={set('rack_location')} />
          {kind === 'real' && (
            <Select label="Login" clearable
              placeholder={refs.data?.length ? 'Choose a login' : 'Add one on the Logins tab first'}
              data={(refs.data ?? []).map((r) => ({ value: r.id, label: r.name }))} value={credentialRef} onChange={setCredentialRef} />
          )}
        </SimpleGrid>
        <Textarea label="Notes" autosize minRows={2} value={form.notes} onChange={set('notes')} />
        <DialogError error={create.error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={create.isPending} disabled={!model || !driverId || !form.name.trim() || !!addressProblem(form.management_address) || (kind === 'real' && !form.management_address.trim())}>Add device</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

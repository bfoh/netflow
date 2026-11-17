import { Alert, Button, Group, Modal, Select, SimpleGrid, Stack, Text, Textarea, TextInput } from '@mantine/core';
import { IconFlask } from '@tabler/icons-react';
import { useState } from 'react';

import { useAction, useDeviceModels } from '../../hooks/queries';
import { api } from '../../services/api';

const PROTOCOLS = [
  { value: 'ssh', label: 'SSH' }, { value: 'https_api', label: 'HTTPS API' },
  { value: 'netconf', label: 'NETCONF' }, { value: 'serial', label: 'Serial console' },
];

const empty = { name: '', role: '', management_address: '', management_protocol: 'ssh', site: '', rack_location: '', notes: '' };

export function AddDeviceModal({ projectId, opened, onClose }:
  { projectId: string; opened: boolean; onClose: () => void }) {
  const models = useDeviceModels();
  const [modelId, setModelId] = useState<string | null>(null);
  const [form, setForm] = useState(empty);
  const create = useAction((body: Parameters<typeof api.createDevice>[1]) => api.createDevice(projectId, body), 'Device added');
  const model = models.data?.find((m) => m.model_id === modelId);
  const set = (k: keyof typeof empty) => (e: { currentTarget: { value: string } }) =>
    setForm({ ...form, [k]: e.currentTarget.value });

  const submit = () => {
    if (!model) return;
    create.mutate({
      ...form,
      manufacturer: model.manufacturer, product_family: model.product_family, model: model.model,
      category: model.category, os_family: model.os_family, driver_id: model.drivers[0],
      environment: 'simulated',
    }, { onSuccess: () => { setForm(empty); setModelId(null); onClose(); } });
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Add network element" size="lg">
      <Stack>
        <Select
          label="Device model" required searchable placeholder="Choose from the device model registry"
          data={(models.data ?? []).map((m) => ({ value: m.model_id, label: `${m.manufacturer} ${m.model} (${m.category})` }))}
          value={modelId} onChange={setModelId}
        />
        {model && (
          <Alert color="violet" icon={<IconFlask size={18} />} variant="light">
            <Text size="sm">
              {model.manufacturer} {model.product_family} · {model.os_family} — support level: <b>{model.support.replaceAll('_', ' ')}</b>.
              The device will use driver <code>{model.drivers[0]}</code> and is created in the <b>simulated</b> environment.
            </Text>
          </Alert>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Device name" required value={form.name} onChange={set('name')} />
          <TextInput label="Network role" placeholder="e.g. access-switch" value={form.role} onChange={set('role')} />
          <TextInput label="Management address" placeholder="e.g. 10.255.0.11" value={form.management_address} onChange={set('management_address')} />
          <Select label="Management protocol" data={PROTOCOLS} value={form.management_protocol}
            onChange={(v) => setForm({ ...form, management_protocol: v ?? 'ssh' })} />
          <TextInput label="Site" value={form.site} onChange={set('site')} />
          <TextInput label="Rack / physical location" value={form.rack_location} onChange={set('rack_location')} />
        </SimpleGrid>
        <Textarea label="Notes" autosize minRows={2} value={form.notes} onChange={set('notes')} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={create.isPending} disabled={!model || !form.name.trim()}>Add device</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

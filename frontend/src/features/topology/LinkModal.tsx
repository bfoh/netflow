import { Button, Group, Modal, SegmentedControl, Select, SimpleGrid, Stack, TagsInput, Text, Textarea, TextInput } from '@mantine/core';
import { useState } from 'react';

import type { TopologyLinkInput } from '../../types/api';

export function LinkModal({ initial, names, onSave, onDelete, onClose, busy, pickDevices }: {
  initial: TopologyLinkInput; names: Record<string, string>; busy: boolean;
  /** Choose both devices in the dialog (a link without dragging, e.g. from the keyboard). */
  pickDevices?: boolean;
  onSave: (l: TopologyLinkInput) => void; onDelete?: () => void; onClose: () => void;
}) {
  const [l, setL] = useState(initial);
  const vlanText = l.vlans.map(String);
  const badVlans = vlanText.some((v) => !/^\d+$/.test(v) || Number(v) < 1 || Number(v) > 4094);
  const devices = Object.entries(names).map(([value, label]) => ({ value, label }));
  const noDevices = !l.a_device_id || !l.b_device_id || l.a_device_id === l.b_device_id;
  return (
    <Modal opened onClose={onClose} title={onDelete ? 'Edit link' : 'New link'}>
      <Stack>
        {pickDevices && (
          <SimpleGrid cols={2}>
            <Select label="From device" data={devices} value={l.a_device_id || null} data-autofocus
              onChange={(v) => setL({ ...l, a_device_id: v ?? '' })} />
            <Select label="To device" data={devices.filter((d) => d.value !== l.a_device_id)} value={l.b_device_id || null}
              onChange={(v) => setL({ ...l, b_device_id: v ?? '' })} />
          </SimpleGrid>
        )}
        <SimpleGrid cols={2}>
          <TextInput label={`Interface on ${names[l.a_device_id] ?? 'A'}`} placeholder="e.g. 1/1/48, port1, Gi1" data-autofocus
            value={l.a_interface} onChange={(e) => setL({ ...l, a_interface: e.currentTarget.value })} />
          <TextInput label={`Interface on ${names[l.b_device_id] ?? 'B'}`}
            value={l.b_interface} onChange={(e) => setL({ ...l, b_interface: e.currentTarget.value })} />
        </SimpleGrid>
        <div>
          <Text size="sm" fw={500} mb={4}>Link mode</Text>
          <SegmentedControl aria-label="Link mode" value={l.mode} onChange={(v) => setL({ ...l, mode: v as TopologyLinkInput['mode'], vlans: v === 'routed' ? [] : l.vlans })}
            data={[{ value: 'routed', label: 'Routed (L3)' }, { value: 'access', label: 'Access (1 VLAN)' }, { value: 'trunk', label: 'Trunk' }]} />
        </div>
        {l.mode !== 'routed' && (
          <TagsInput label="VLANs" placeholder="type a VLAN ID and press Enter" value={vlanText}
            error={badVlans ? 'VLAN IDs are numbers 1-4094' : undefined}
            onChange={(v) => setL({ ...l, vlans: v.filter((x) => /^\d+$/.test(x)).map(Number) })} />
        )}
        <Textarea label="Notes" autosize minRows={1} value={l.notes} onChange={(e) => setL({ ...l, notes: e.currentTarget.value })} />
        <Text size="xs" c="dimmed">A link records the intended design. It does not prove that a cable exists.</Text>
        <Group justify="space-between">
          {onDelete ? <Button color="red" variant="subtle" onClick={onDelete}>Delete link</Button> : <span />}
          <Group>
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button loading={busy} disabled={noDevices || !l.a_interface.trim() || !l.b_interface.trim() || badVlans} onClick={() => onSave(l)}>Save</Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}

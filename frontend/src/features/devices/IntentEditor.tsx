import { ActionIcon, Alert, Button, Card, Group, NumberInput, Stack, Switch, Table, Text, TextInput, Title } from '@mantine/core';
import { IconAlertTriangle, IconPlus, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';

import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import { normalizeIntent } from '../../services/intent';
import type { Device, DeviceIntent } from '../../types/api';

const orNull = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null);

/** Structured, vendor-neutral intent editor (hostname, VLANs, L3 interfaces, static routes). */
export function IntentEditor({ device }: { device: Device }) {
  // Prefer the hostname read from the device, so a new intent does not rename it by accident.
  const observedHostname = typeof device.observed_facts?.hostname === 'string' ? device.observed_facts.hostname : null;
  const [intent, setIntent] = useState<DeviceIntent>(() => normalizeIntent(device.intent, observedHostname ?? device.name));
  const renames = !!observedHostname && intent.hostname.trim() !== '' && intent.hostname.trim() !== observedHostname;
  const save = useAction((i: DeviceIntent) => api.setIntent(device.id, i), 'Intent saved');
  const update = <K extends keyof DeviceIntent>(k: K, v: DeviceIntent[K]) => setIntent({ ...intent, [k]: v });
  const patchRow = <K extends 'vlans' | 'interfaces' | 'static_routes'>(k: K, i: number, row: Partial<DeviceIntent[K][number]>) =>
    update(k, intent[k].map((r, j) => (j === i ? { ...r, ...row } : r)) as DeviceIntent[K]);
  const removeRow = (k: 'vlans' | 'interfaces' | 'static_routes', i: number) =>
    update(k, intent[k].filter((_, j) => j !== i) as never);

  const submit = () => save.mutate({
    hostname: intent.hostname.trim(),
    vlans: intent.vlans.map((v) => ({ vlan_id: Number(v.vlan_id), name: orNull(v.name) })),
    interfaces: intent.interfaces.map((i) => ({ interface: i.interface.trim(), address: i.address.trim(), description: orNull(i.description), enabled: i.enabled ?? true })),
    static_routes: intent.static_routes.map((r) => ({ prefix: r.prefix.trim(), next_hop: r.next_hop.trim(), egress_interface: orNull(r.egress_interface) })),
  });

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Describe what this device should do, independent of vendor syntax. Configuration generation checks
        the intent and reports anything the selected platform cannot express.
      </Text>
      <Card withBorder>
        <TextInput label="Hostname" required maw={320} value={intent.hostname} onChange={(e) => update('hostname', e.currentTarget.value)} />
        {renames && (
          <Alert color="orange" mt="sm" icon={<IconAlertTriangle size={16} />} title="This intent renames the device">
            The device currently reports hostname <b>{observedHostname}</b>. A plan with these settings sets it to <b>{intent.hostname}</b>.
            Keep the current name unless you mean to rename it.
            <Button size="xs" variant="light" ml="sm" onClick={() => update('hostname', observedHostname!)}>Use {observedHostname}</Button>
          </Alert>
        )}
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="xs"><Title order={5}>VLANs</Title>
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => update('vlans', [...intent.vlans, { vlan_id: 1, name: '' }])}>Add VLAN</Button></Group>
        <Table>
          <Table.Thead><Table.Tr><Table.Th w={140}>VLAN ID</Table.Th><Table.Th>Name</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {intent.vlans.map((v, i) => (
              <Table.Tr key={i}>
                <Table.Td><NumberInput aria-label="VLAN ID" min={1} max={4094} value={v.vlan_id} onChange={(n) => patchRow('vlans', i, { vlan_id: Number(n) })} /></Table.Td>
                <Table.Td><TextInput aria-label="VLAN name" value={v.name ?? ''} onChange={(e) => patchRow('vlans', i, { name: e.currentTarget.value })} /></Table.Td>
                <Table.Td><ActionIcon variant="subtle" color="red" aria-label="Remove VLAN" onClick={() => removeRow('vlans', i)}><IconTrash size={16} /></ActionIcon></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="xs"><Title order={5}>Layer-3 interfaces</Title>
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => update('interfaces', [...intent.interfaces, { interface: '', address: '', description: '', enabled: true }])}>Add interface</Button></Group>
        <Text size="xs" c="dimmed" mb="xs">Use the platform interface name (e.g. port1, GigabitEthernet1) or <code>vlanN</code> for a VLAN interface. Address in CIDR form.</Text>
        <Table.ScrollContainer minWidth={640}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Interface</Table.Th><Table.Th>Address (CIDR)</Table.Th><Table.Th>Description</Table.Th><Table.Th w={80}>Enabled</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {intent.interfaces.map((x, i) => (
                <Table.Tr key={i}>
                  <Table.Td><TextInput aria-label="Interface" value={x.interface} onChange={(e) => patchRow('interfaces', i, { interface: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><TextInput aria-label="Address" placeholder="10.0.0.1/24" value={x.address} onChange={(e) => patchRow('interfaces', i, { address: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><TextInput aria-label="Description" value={x.description ?? ''} onChange={(e) => patchRow('interfaces', i, { description: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><Switch aria-label="Enabled" checked={x.enabled ?? true} onChange={(e) => patchRow('interfaces', i, { enabled: e.currentTarget.checked })} /></Table.Td>
                  <Table.Td><ActionIcon variant="subtle" color="red" aria-label="Remove interface" onClick={() => removeRow('interfaces', i)}><IconTrash size={16} /></ActionIcon></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="xs"><Title order={5}>Static routes</Title>
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => update('static_routes', [...intent.static_routes, { prefix: '0.0.0.0/0', next_hop: '', egress_interface: '' }])}>Add route</Button></Group>
        <Table.ScrollContainer minWidth={560}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Prefix</Table.Th><Table.Th>Next hop</Table.Th><Table.Th>Egress interface (optional)</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {intent.static_routes.map((r, i) => (
                <Table.Tr key={i}>
                  <Table.Td><TextInput aria-label="Prefix" value={r.prefix} onChange={(e) => patchRow('static_routes', i, { prefix: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><TextInput aria-label="Next hop" value={r.next_hop} onChange={(e) => patchRow('static_routes', i, { next_hop: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><TextInput aria-label="Egress interface" value={r.egress_interface ?? ''} onChange={(e) => patchRow('static_routes', i, { egress_interface: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><ActionIcon variant="subtle" color="red" aria-label="Remove route" onClick={() => removeRow('static_routes', i)}><IconTrash size={16} /></ActionIcon></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Group><Button onClick={submit} loading={save.isPending} disabled={!intent.hostname.trim()}>Save intent</Button></Group>
    </Stack>
  );
}

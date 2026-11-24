import { ActionIcon, Anchor, Button, Card, Checkbox, Group, Menu, Select, Table, Text, Tooltip } from '@mantine/core';
import { IconDots, IconLock } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../../components/Badges';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import type { Device, OperationResult } from '../../types/api';
import { humanize, stateLabel } from '../../services/labels';

/**
 * Inventory table with multi-select and bulk actions.
 *
 * Only read-only actions run from here. Anything that changes a device goes through a
 * deployment plan (validate, preview, approve, execute), so there is no
 * "enable impacting actions" switch: the plan itself is the gate.
 */
const BULK = [
  { value: 'get_facts', label: 'Retrieve device information' },
  { value: 'backup_configuration', label: 'Back up configuration' },
  { value: 'generate', label: 'Generate configuration' },
  { value: 'deploy', label: 'Make a plan…' },
];

export function DeviceTable({ devices, showProject, projectNames }:
  { devices: Device[]; showProject?: boolean; projectNames?: Map<string, string> }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [action, setAction] = useState<string | null>('get_facts');
  const navigate = useNavigate();
  const ids = new Set(devices.map((d) => d.id));
  const sel = selected.filter((id) => ids.has(id));
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const bulk = useAction(async ({ op, targets }: { op: string; targets: string[] }) => {
    const results: (OperationResult | { status: string })[] = [];
    for (const id of targets) {
      if (op === 'generate') {
        const r = await api.generateConfig(id);
        results.push({ status: r.ok ? 'success' : 'failed' });
      } else {
        results.push(await api.runOperation(id, op));
      }
    }
    return results;
  }, (rs) => `${rs.filter((r) => r.status === 'success').length} of ${rs.length} succeeded`);

  const single = useAction(({ id, op }: { id: string; op: string }) =>
    op === 'generate' ? api.generateConfig(id).then((r) => ({ status: r.ok ? 'success' : 'failed', message: '' }))
      : api.runOperation(id, op),
  (r) => `${stateLabel(r.status)}${r.message ? ` — ${r.message}` : ''}`);

  const perform = () => {
    if (!action || sel.length === 0) return;
    if (action === 'deploy') {
      const projects = new Set(devices.filter((d) => sel.includes(d.id)).map((d) => d.project_id));
      if (projects.size !== 1) return;
      void navigate(`/deployments?project=${[...projects][0]}&devices=${sel.join(',')}`);
      return;
    }
    bulk.mutate({ op: action, targets: sel });
  };
  const multiProject = action === 'deploy'
    && new Set(devices.filter((d) => sel.includes(d.id)).map((d) => d.project_id)).size > 1;

  return (
    <Card withBorder padding={0}>
      <Group justify="space-between" p="sm" wrap="wrap">
        <Group gap="xs">
          <Text size="sm">Selected: <b>{sel.length}</b></Text>
          <Button size="compact-sm" variant="subtle" disabled={sel.length === 0} onClick={() => setSelected([])}>Clear</Button>
        </Group>
        <Group gap="xs">
          <Select size="xs" data={BULK} value={action} onChange={setAction} aria-label="Bulk action" w={230} />
          <Tooltip label="A plan can only include devices from one system" disabled={!multiProject}>
            <Button size="xs" onClick={perform} disabled={sel.length === 0 || multiProject} loading={bulk.isPending}>Perform</Button>
          </Tooltip>
        </Group>
      </Group>
      <Table.ScrollContainer minWidth={900}>
        <Table highlightOnHover verticalSpacing="xs" horizontalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={36}>
                <Checkbox aria-label="Select all" checked={sel.length > 0 && sel.length === devices.length}
                  indeterminate={sel.length > 0 && sel.length < devices.length}
                  onChange={() => setSelected(sel.length === devices.length ? [] : devices.map((d) => d.id))} />
              </Table.Th>
              <Table.Th>Name</Table.Th>
              {showProject && <Table.Th>System</Table.Th>}
              <Table.Th>Vendor / model</Table.Th><Table.Th>Category</Table.Th><Table.Th>Role</Table.Th>
              <Table.Th>Address</Table.Th><Table.Th>Kind</Table.Th><Table.Th>Status</Table.Th><Table.Th w={40} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {devices.map((d) => (
              <Table.Tr key={d.id} bg={sel.includes(d.id) ? 'var(--mantine-primary-color-light)' : undefined}>
                <Table.Td><Checkbox aria-label={`Select ${d.name}`} checked={sel.includes(d.id)} onChange={() => toggle(d.id)} /></Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    <Anchor component={Link} to={`/devices/${d.id}`} fw={600} size="sm">{d.name}</Anchor>
                    {d.locked_by_deployment_id && <Tooltip label="A plan is running on this device"><IconLock size={14} /></Tooltip>}
                  </Group>
                </Table.Td>
                {showProject && <Table.Td><Anchor component={Link} to={`/projects/${d.project_id}`} size="sm">{projectNames?.get(d.project_id) ?? '—'}</Anchor></Table.Td>}
                <Table.Td><Text size="sm">{d.manufacturer} {d.model}</Text></Table.Td>
                <Table.Td><Text size="sm">{humanize(d.category)}</Text></Table.Td>
                <Table.Td><Text size="sm">{d.role || '—'}</Text></Table.Td>
                <Table.Td><Text size="sm" ff="monospace">{d.management_address || '—'}</Text></Table.Td>
                <Table.Td><EnvironmentBadge env={d.environment} /></Table.Td>
                <Table.Td><StateBadge state={d.deployment_status} /></Table.Td>
                <Table.Td>
                  <Menu position="bottom-end" withinPortal>
                    <Menu.Target><ActionIcon variant="subtle" aria-label={`Actions for ${d.name}`}><IconDots size={16} /></ActionIcon></Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item component={Link} to={`/devices/${d.id}`}>Open details</Menu.Item>
                      <Menu.Label>Read-only</Menu.Label>
                      <Menu.Item onClick={() => single.mutate({ id: d.id, op: 'check_reachability' })}>Test connection</Menu.Item>
                      <Menu.Item onClick={() => single.mutate({ id: d.id, op: 'get_facts' })}>Retrieve device information</Menu.Item>
                      <Menu.Item onClick={() => single.mutate({ id: d.id, op: 'backup_configuration' })}>Back up configuration</Menu.Item>
                      <Menu.Item onClick={() => single.mutate({ id: d.id, op: 'generate' })}>Generate configuration</Menu.Item>
                      <Menu.Label>Changes the device</Menu.Label>
                      <Menu.Item onClick={() => void navigate(`/deployments?project=${d.project_id}&devices=${d.id}`)}>Make a plan…</Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
            {devices.length === 0 && (
              <Table.Tr><Table.Td colSpan={showProject ? 10 : 9}><Text c="dimmed" ta="center" p="md">No devices yet. Open a system and choose Add device.</Text></Table.Td></Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

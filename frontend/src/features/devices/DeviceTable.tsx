import { Anchor, Button, Card, Checkbox, Group, Select, Table, Text, Tooltip } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { EnvironmentBadge, StateBadge } from '../../components/Badges';
import { useAction } from '../../hooks/queries';
import { useConfirm } from '../../hooks/useConfirm';
import { api, type Reachability } from '../../services/api';
import { DeviceMenu } from './DeviceMenu';
import { openDeviceMenu } from './openDeviceMenu';
import { ReachDot } from './ReachDot';
import type { Device, OperationResult } from '../../types/api';
import { humanize } from '../../services/labels';
import { paths } from '../../paths';

/**
 * Inventory table with multi-select and bulk actions.
 *
 * Only read-only actions run from here. Anything that changes a device goes through a
 * plan (check, preview, approve, run), so there is no "enable impacting actions" switch:
 * the plan itself is the gate. Deleting removes the device from UNDM only (confirmed).
 */
const BULK = [
  { value: 'get_facts', label: 'Retrieve device information' },
  { value: 'backup_configuration', label: 'Back up configuration' },
  { value: 'generate', label: 'Generate configuration' },
  { value: 'deploy', label: 'Make a plan…' },
  { value: 'delete', label: 'Delete devices…' },
];

export function DeviceTable({ devices, showProject, projectNames, selected: outer, onSelectedChange, reach }: {
  devices: Device[]; showProject?: boolean; projectNames?: Map<string, string>;
  /** Selection shared with another view (the system tree). */
  selected?: string[]; onSelectedChange?: (ids: string[]) => void;
  /** Live reachability by device id, when watched (D-099). */
  reach?: Map<string, Reachability['state']>;
}) {
  const [inner, setInner] = useState<string[]>([]);
  const selected = outer ?? inner;
  const setSelected = (next: string[] | ((s: string[]) => string[])) => {
    const value = typeof next === 'function' ? next(selected) : next;
    if (onSelectedChange) onSelectedChange(value); else setInner(value);
  };
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

  const [ask, confirmDialog] = useConfirm();
  const remove = useAction(async (targets: Device[]) => {
    const failed: string[] = [];
    for (const d of targets) {
      try { await api.deleteDevice(d.id); } catch (e) { failed.push(`${d.name}: ${(e as Error).message}`); }
    }
    if (failed.length) throw new Error(`Not deleted: ${failed.join('; ')}`);
    return targets.length;
  }, (n) => `${n} ${n === 1 ? 'device' : 'devices'} deleted`, { errorInDialog: true });
  const askDelete = (targets: Device[]) => ask({
    title: targets.length === 1 ? `Delete ${targets[0].name}?` : `Delete ${targets.length} devices?`,
    confirmLabel: 'Delete', typed: targets.length === 1 ? targets[0].name : 'delete',
    message: <>
      {targets.length > 1 && <>{targets.map((d) => d.name).join(', ')}.<br /></>}
      Their files, backups and history are removed from UNDM; the devices themselves are not touched. Their logins stay on the
      system page. A device a plan is running on cannot be deleted.
    </>,
    onConfirm: async () => { await remove.mutateAsync(targets); setSelected([]); },
  });

  const perform = () => {
    if (!action || sel.length === 0) return;
    if (action === 'delete') { askDelete(devices.filter((d) => sel.includes(d.id))); return; }
    if (action === 'deploy') {
      const projects = new Set(devices.filter((d) => sel.includes(d.id)).map((d) => d.project_id));
      if (projects.size !== 1) return;
      void navigate(paths.planNew({ system: [...projects][0], devices: sel.join(',') }));
      return;
    }
    bulk.mutate({ op: action, targets: sel });
  };
  const multiProject = action === 'deploy'
    && new Set(devices.filter((d) => sel.includes(d.id)).map((d) => d.project_id)).size > 1;

  return (
    <Card withBorder padding={0}>
      {confirmDialog}
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
              <Table.Th>Address</Table.Th><Table.Th>Kind</Table.Th><Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {devices.map((d) => (
              <Table.Tr key={d.id} bg={sel.includes(d.id) ? 'var(--mantine-primary-color-light)' : undefined}
                onContextMenu={openDeviceMenu}>
                <Table.Td><Checkbox aria-label={`Select ${d.name}`} checked={sel.includes(d.id)} onChange={() => toggle(d.id)} /></Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    {reach && <ReachDot state={reach.get(d.id)} />}
                    <DeviceMenu device={d} onDelete={() => askDelete([d])} />
                    <Anchor component={Link} to={paths.device(d.id)} fw={600} size="sm">{d.name}</Anchor>
                    {d.locked_by_deployment_id && <Tooltip label="A plan is running on this device"><IconLock size={14} /></Tooltip>}
                  </Group>
                </Table.Td>
                {showProject && <Table.Td><Anchor component={Link} to={paths.system(d.project_id)} size="sm">{projectNames?.get(d.project_id) ?? '—'}</Anchor></Table.Td>}
                <Table.Td><Text size="sm">{d.manufacturer} {d.model}</Text></Table.Td>
                <Table.Td><Text size="sm">{humanize(d.category)}</Text></Table.Td>
                <Table.Td><Text size="sm">{d.role || '—'}</Text></Table.Td>
                <Table.Td><Text size="sm" ff="monospace">{d.management_address || '—'}</Text></Table.Td>
                <Table.Td><EnvironmentBadge env={d.environment} /></Table.Td>
                <Table.Td><StateBadge state={d.deployment_status} /></Table.Td>
              </Table.Tr>
            ))}
            {devices.length === 0 && (
              <Table.Tr><Table.Td colSpan={showProject ? 9 : 8}><Text c="dimmed" ta="center" p="md">No devices yet. Open a system and choose Add device.</Text></Table.Td></Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

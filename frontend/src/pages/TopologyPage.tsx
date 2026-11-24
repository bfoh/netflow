import '@xyflow/react/dist/style.css';

import { Badge, Button, Card, Grid, Group, Select, Stack, Table, Text, Title, useComputedColorScheme } from '@mantine/core';
import { IconCircleCheck, IconLayoutGrid } from '@tabler/icons-react';
import {
  Background, ConnectionMode, Controls, type Connection, type Edge, MarkerType, Position, ReactFlow, ReactFlowProvider,
  useNodesState,
} from '@xyflow/react';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';

import { PageHeader, QueryState } from '../components/Page';
import { DeviceNode, type DeviceNodeType } from '../features/topology/DeviceNode';
import { LinkModal } from '../features/topology/LinkModal';
import { useAction, useProjects, useTopology } from '../hooks/queries';
import { api } from '../services/api';
import type { Topology, TopologyLink, TopologyLinkInput } from '../types/api';
import { EmptyState } from '../components/EmptyState';

const nodeTypes = { device: DeviceNode };
const ROW: Record<string, number> = { firewall: 0, router: 1, switch: 2 };
const MODE_COLOR: Record<string, string> = { routed: '#7048e8', trunk: '#1c7ed6', access: '#0ca678' };

/** Default positions for devices never placed: one row per category. */
function layout(topo: Topology, force = false): DeviceNodeType[] {
  const perRow: Record<number, number> = {};
  return topo.nodes.map((n) => {
    const row = ROW[n.category] ?? 3;
    const col = (perRow[row] = (perRow[row] ?? -1) + 1);
    const auto = { x: 40 + col * 240, y: 40 + row * 170 };
    const position = !force && n.x !== null && n.y !== null ? { x: n.x, y: n.y } : auto;
    return { id: n.device_id, type: 'device', position, data: { device: n } };
  });
}

type XY = { x: number; y: number };

/** Attach a link to the sides of the two devices that face each other. */
function facingHandles(a: XY | undefined, b: XY | undefined): [string, string] {
  if (!a || !b) return [Position.Bottom, Position.Top];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? [Position.Right, Position.Left] : [Position.Left, Position.Right];
  return dy > 0 ? [Position.Bottom, Position.Top] : [Position.Top, Position.Bottom];
}

function edgeFor(l: TopologyLink, hasError: boolean, pos: Record<string, XY>): Edge {
  const vl = l.vlans.length ? ` [${l.vlans.join(',')}]` : '';
  const [sourceHandle, targetHandle] = facingHandles(pos[l.a_device_id], pos[l.b_device_id]);
  return {
    id: l.id, source: l.a_device_id, target: l.b_device_id, sourceHandle, targetHandle,
    label: `${l.a_interface} ↔ ${l.b_interface}${vl}`,
    style: { stroke: hasError ? '#e03131' : MODE_COLOR[l.mode], strokeWidth: 2 },
    labelStyle: { fontSize: 11 }, labelBgPadding: [4, 2], labelBgBorderRadius: 4,
    markerEnd: undefined, interactionWidth: 16, data: { link: l },
  };
}

function Canvas({ projectId, topo }: { projectId: string; topo: Topology }) {
  const scheme = useComputedColorScheme('light');
  const [nodes, setNodes, onNodesChange] = useNodesState<DeviceNodeType>(layout(topo));
  const [editing, setEditing] = useState<{ id?: string; link: TopologyLinkInput; pick?: boolean } | null>(null);
  const names = useMemo(() => Object.fromEntries(topo.nodes.map((n) => [n.device_id, n.name])), [topo.nodes]);
  const errorLinks = new Set(topo.issues.filter((i) => i.severity === 'error' && i.path.startsWith('links/')).map((i) => i.path.slice(6)));
  const positions = Object.fromEntries(nodes.map((n) => [n.id, n.position]));
  const edges = topo.links.map((l) => edgeFor(l, errorLinks.has(l.id), positions));

  // Keep node data/positions in sync when the topology changes (new devices, saved layout).
  const signature = topo.nodes.map((n) => `${n.device_id}:${n.x}:${n.y}:${n.name}`).join('|');
  useEffect(() => { setNodes(layout(topo)); }, [signature]); // eslint-disable-line react-hooks/exhaustive-deps

  const savePositions = useAction((pos: Record<string, { x: number; y: number }>) => api.savePositions(projectId, pos));
  const create = useAction((l: TopologyLinkInput) => api.createLink(projectId, l), 'Link added');
  const update = useAction(({ id, l }: { id: string; l: TopologyLinkInput }) => api.updateLink(id, l), 'Link updated');
  const del = useAction((id: string) => api.deleteLink(id), 'Link deleted');

  const onConnect = (c: Connection) => {
    if (!c.source || !c.target || c.source === c.target) return;
    setEditing({ link: { a_device_id: c.source, a_interface: '', b_device_id: c.target, b_interface: '', mode: 'routed', vlans: [], notes: '' } });
  };
  const autoArrange = () => {
    const arranged = layout(topo, true);
    setNodes(arranged);
    savePositions.mutate(Object.fromEntries(arranged.map((n) => [n.id, n.position])));
  };

  return (
    <>
      <Group mb="xs">
        <Button size="xs" variant="default" leftSection={<IconLayoutGrid size={14} />} onClick={autoArrange}>Auto-arrange</Button>
        <Button size="xs" variant="default" onClick={() => setEditing({ pick: true, link: { a_device_id: '', a_interface: '', b_device_id: '', b_interface: '', mode: 'routed', vlans: [], notes: '' } })}>Add link…</Button>
        <Text size="xs" c="dimmed">Or drag from a device's edge dot to another device. Click a link to edit it. Drag devices to arrange them.</Text>
      </Group>
      <Card withBorder padding={0} h={560}>
        <ReactFlow
          nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
          onConnect={onConnect} connectionMode={ConnectionMode.Loose}
          onNodeDragStop={(_, node, dragged) => {
            const moved = dragged?.length ? dragged : [node];
            savePositions.mutate(Object.fromEntries(moved.map((n) => [n.id, n.position])));
          }}
          onEdgeClick={(_, edge) => {
            const l = (edge.data as { link: TopologyLink }).link;
            const { id, ...rest } = l;
            setEditing({ id, link: rest });
          }}
          defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed, width: 0, height: 0 } }}
          forceColorMode={scheme} fitView fitViewOptions={{ padding: 0.2, maxZoom: 1.2 }}
        >
          <Background gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Card>
      <Group gap="md" mt={6} aria-label="Legend">
        {Object.entries({ routed: 'Routed (L3)', trunk: 'Trunk', access: 'Access (one VLAN)' }).map(([m, label]) => (
          <Group key={m} gap={4}><span style={{ width: 18, height: 3, background: MODE_COLOR[m], display: 'inline-block' }} /><Text size="xs">{label}</Text></Group>
        ))}
        <Group gap={4}><span style={{ width: 18, height: 3, background: '#e03131', display: 'inline-block' }} /><Text size="xs">Has a problem (see the list)</Text></Group>
      </Group>
      {editing && (
        <LinkModal initial={editing.link} names={names} busy={create.isPending || update.isPending} pickDevices={editing.pick}
          onClose={() => setEditing(null)}
          onDelete={editing.id ? () => del.mutate(editing.id!, { onSuccess: () => setEditing(null) }) : undefined}
          onSave={(l) => (editing.id
            ? update.mutate({ id: editing.id, l }, { onSuccess: () => setEditing(null) })
            : create.mutate(l, { onSuccess: () => setEditing(null) }))} />
      )}
    </>
  );
}

function Side({ topo }: { topo: Topology }) {
  const names = Object.fromEntries(topo.nodes.map((n) => [n.device_id, n.name]));
  const errors = topo.issues.filter((i) => i.severity === 'error');
  return (
    <Stack>
      <Card withBorder>
        <Group justify="space-between" mb="xs">
          <Title order={2} size="h5">Validation</Title>
          {topo.issues.length === 0
            ? <Badge color="teal" variant="light" leftSection={<IconCircleCheck size={12} />}>no issues</Badge>
            : <Badge color={errors.length ? 'red' : 'yellow'} variant="light">{errors.length} errors · {topo.issues.length - errors.length} warnings</Badge>}
        </Group>
        <Stack gap={6}>
          {topo.issues.map((i, n) => (
            <Text key={n} size="sm" c={i.severity === 'error' ? 'red' : 'yellow.8'}>
              <b>{i.severity}</b> · {i.message}
            </Text>
          ))}
          {topo.issues.length === 0 && <Text size="sm" c="dimmed">Checks: interfaces used twice, self links, subnet mismatch, VLANs not defined, duplicate IPs, isolated devices.</Text>}
        </Stack>
      </Card>
      <Card withBorder padding={0}>
        <Title order={2} size="h5" p="sm" pb={0}>Links ({topo.links.length})</Title>
        <Table.ScrollContainer minWidth={520}>
          <Table verticalSpacing={4} horizontalSpacing="sm">
            <Table.Tbody>
              {topo.links.map((l) => (
                <Table.Tr key={l.id}>
                  <Table.Td><Text size="xs">{names[l.a_device_id]}:{l.a_interface}</Text></Table.Td>
                  <Table.Td><Text size="xs">{names[l.b_device_id]}:{l.b_interface}</Text></Table.Td>
                  <Table.Td><Text size="xs">{l.mode}{l.vlans.length ? ` ${l.vlans.join(',')}` : ''}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </Stack>
  );
}

export function TopologyPage() {
  const [params, setParams] = useSearchParams();
  const projects = useProjects();
  const projectId = params.get('project') ?? projects.data?.[0]?.id ?? '';
  const topo = useTopology(projectId);
  return (
    <>
      <PageHeader title="Topology" description="Design devices and the links between their interfaces. The graph, not the drawing, is what UNDM validates." />
      <Group mb="md">
        <Select label="System" w="100%" maw={320} data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
          value={projectId || null} onChange={(v) => v && setParams({ project: v })} allowDeselect={false} />
      </Group>
      <QueryState isLoading={topo.isLoading} error={topo.error} />
      {topo.data && topo.data.nodes.length === 0 && (
        <EmptyState>This system has no devices yet. Add devices on the system page first.</EmptyState>
      )}
      {topo.data && topo.data.nodes.length > 0 && (
        <Grid>
          <Grid.Col span={{ base: 12, lg: 9 }}>
            <ReactFlowProvider><Canvas key={projectId} projectId={projectId} topo={topo.data} /></ReactFlowProvider>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 3 }}><Side topo={topo.data} /></Grid.Col>
        </Grid>
      )}
    </>
  );
}

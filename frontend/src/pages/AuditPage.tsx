import { Accordion, Anchor, Button, Card, Code, Group, Modal, Select, Table, Text, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { type ReactNode, useState } from 'react';
import { Link } from 'react-router';

import { StateBadge } from '../components/Badges';
import { ActionsHeader, DataTable } from '../components/DataTable';
import { PageHeader } from '../components/Page';
import { useAllDevices, useAudit, useProjects } from '../hooks/queries';
import { paths } from '../paths';
import { fmtDate } from '../services/format';
import { auditActionLabel, humanize, stateLabel } from '../services/labels';
import type { AuditEvent } from '../types/api';
import { SWITCHES } from '../features/settings/useSafetySwitch';

/** A detail value in words: short scalars as they are, lists joined, objects summarised. */
function words(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (Array.isArray(v)) return v.length === 0 ? 'none' : v.every((x) => typeof x !== 'object') ? v.join(', ') : `${v.length} entries`;
  if (typeof v === 'object') return `${Object.keys(v as object).length} values (see Technical details)`;
  const s = String(v);
  return s.length > 80 ? `${s.slice(0, 80)}…` : s;
}

/**
 * Advanced → Audit log (D-122): what happened, by whom, on what, in words. Device, system and
 * plan names link to them; the recorded values are under "Technical details".
 */
export function AuditPage() {
  const audit = useAudit(undefined, 500);
  const devices = useAllDevices();
  const projects = useProjects();
  const [q, setQ] = useState('');
  const [what, setWhat] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const deviceName = new Map((devices.data ?? []).map((d) => [d.id, d.name]));
  const systemName = new Map((projects.data ?? []).map((p) => [p.id, p.name]));

  /** What an entry is about, by name, linked where UNDM has a page for it. */
  const on = (a: AuditEvent): { text: string; node: ReactNode } => {
    const id = a.target_id;
    const link = (to: string, text: string) => ({ text, node: <Anchor component={Link} to={to} size="sm">{text}</Anchor> });
    switch (a.target_type) {
      case 'device': return deviceName.has(id) ? link(paths.device(id), deviceName.get(id)!) : { text: 'a deleted device', node: 'a deleted device' };
      case 'project': return systemName.has(id) ? link(paths.system(id), systemName.get(id)!) : { text: 'a deleted system', node: 'a deleted system' };
      case 'deployment': return link(paths.plan(id), 'its plan');
      case 'staging_plan': return link(paths.staging(id), 'its staging plan');
      case 'policy': { const s = SWITCHES.find((x) => x.key === id); const t = s?.label ?? humanize(id); return { text: t, node: t }; }
      default: { const t = humanize(a.target_type); return { text: t, node: t }; }
    }
  };
  const labels = [...new Set((audit.data ?? []).map((a) => auditActionLabel(a.action)))].sort();
  const outcomes = [...new Set((audit.data ?? []).map((a) => a.outcome))].sort();
  const needle = q.trim().toLowerCase();
  const rows = (audit.data ?? []).filter((a) => (!what || auditActionLabel(a.action) === what) && (!result || a.outcome === result)
    && (!needle || [a.actor, auditActionLabel(a.action), on(a).text, stateLabel(a.outcome), JSON.stringify(a.details)]
      .some((v) => v.toLowerCase().includes(needle))));
  return (
    <>
      <PageHeader title="Audit log"
        description="Everything done in UNDM: when, who, what, on what, and the result. Passwords are never recorded." />
      <Card mb="md">
        <Group align="flex-end" wrap="wrap">
          <TextInput label="Search" placeholder="A name, a device, a word in the details" leftSection={<IconSearch size={16} />}
            value={q} onChange={(e) => setQ(e.currentTarget.value)} w={320} />
          <Select label="What" placeholder="Everything" clearable searchable w={280} data={labels} value={what} onChange={setWhat} />
          <Select label="Result" placeholder="Any result" clearable w={200}
            data={outcomes.map((o) => ({ value: o, label: stateLabel(o) }))} value={result} onChange={setResult} />
        </Group>
      </Card>
      <Card padding={0}>
        <DataTable label="Audit log" loading={audit.isLoading} error={audit.error} rowCount={rows.length} minWidth={820}
          empty={audit.data?.length ? 'Nothing matches these filters.' : 'Nothing recorded yet.'}>
          <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>Who</Table.Th><Table.Th>What</Table.Th><Table.Th>On</Table.Th><Table.Th>Result</Table.Th><ActionsHeader label="Details" /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {rows.map((a) => (
              <Table.Tr key={a.id}>
                <Table.Td><Text size="sm">{fmtDate(a.timestamp)}</Text></Table.Td>
                <Table.Td><Text size="sm">{a.actor}</Text></Table.Td>
                <Table.Td><Text size="sm">{auditActionLabel(a.action)}</Text></Table.Td>
                <Table.Td><Text size="sm" component="div">{on(a).node}</Text></Table.Td>
                <Table.Td><StateBadge state={a.outcome} /></Table.Td>
                <Table.Td>{Object.keys(a.details).length > 0 && (
                  <Button size="compact-xs" variant="subtle" onClick={() => setOpen(a)}
                    aria-label={`Details of ${auditActionLabel(a.action)}, ${fmtDate(a.timestamp)}`}>Details</Button>)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </DataTable>
      </Card>
      <Modal opened={open !== null} onClose={() => setOpen(null)} size="xl"
        title={open ? `${auditActionLabel(open.action)} · ${fmtDate(open.timestamp)}` : ''}>
        {open && (
          <>
            <Text size="sm" mb="xs">{open.actor} · {on(open).node} · {stateLabel(open.outcome)}</Text>
            <Table verticalSpacing={4} mb="sm" aria-label="Recorded details"><Table.Tbody>
              {Object.entries(open.details).map(([k, v]) => (
                <Table.Tr key={k}><Table.Th scope="row" w={220} fw={400} c="dimmed" style={{ verticalAlign: 'top' }}>{humanize(k)}</Table.Th>
                  <Table.Td><Text size="sm" style={{ wordBreak: 'break-word' }}>{words(v)}</Text></Table.Td></Table.Tr>
              ))}
            </Table.Tbody></Table>
            <Accordion variant="contained"><Accordion.Item value="raw">
              <Accordion.Control><Text size="sm">Technical details</Text></Accordion.Control>
              <Accordion.Panel>
                <Text size="xs" c="dimmed" mb={4}>Action <code>{open.action}</code> on {open.target_type} <code>{open.target_id}</code></Text>
                <Code block style={{ maxHeight: '50vh', overflow: 'auto' }}>{JSON.stringify(open.details, null, 2)}</Code>
              </Accordion.Panel>
            </Accordion.Item></Accordion>
          </>
        )}
      </Modal>
    </>
  );
}

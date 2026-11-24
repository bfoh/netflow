import { Button, Card, Code, Group, Modal, Table, Text, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';

import { StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { auditActionLabel, humanize } from '../services/labels';
import { useAudit } from '../hooks/queries';
import type { AuditEvent } from '../types/api';

export function AuditPage() {
  const audit = useAudit(undefined, 500);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const needle = q.trim().toLowerCase();
  const rows = (audit.data ?? []).filter((a) => !needle
    || [a.actor, a.action, auditActionLabel(a.action), a.target_type, a.target_id, a.outcome, JSON.stringify(a.details)]
      .some((v) => v.toLowerCase().includes(needle)));
  return (
    <>
      <PageHeader title="Audit log"
        description="Everything done in UNDM: who did it, when, on what, and the result. Passwords are never recorded." />
      <Group mb="md"><TextInput placeholder="Filter by name, action, device or details" leftSection={<IconSearch size={16} />}
        value={q} onChange={(e) => setQ(e.currentTarget.value)} w={360} aria-label="Filter audit events" /></Group>
      <QueryState isLoading={audit.isLoading} error={audit.error} />
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={820}>
          <Table verticalSpacing={6} horizontalSpacing="md" striped>
            <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>By</Table.Th><Table.Th>Action</Table.Th><Table.Th>On</Table.Th><Table.Th>Result</Table.Th><Table.Th>Details</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {rows.map((a) => (
                <Table.Tr key={a.id}>
                  <Table.Td><Text size="sm">{fmtDate(a.timestamp)}</Text></Table.Td>
                  <Table.Td>{a.actor}</Table.Td>
                  <Table.Td><Text size="sm">{auditActionLabel(a.action)}</Text><Text size="xs" c="dimmed" ff="monospace">{a.action}</Text></Table.Td>
                  <Table.Td><Text size="sm">{humanize(a.target_type)} <Text span c="dimmed" ff="monospace">{a.target_type === 'policy' ? a.target_id : a.target_id.slice(0, 8)}</Text></Text></Table.Td>
                  <Table.Td><StateBadge state={a.outcome} /></Table.Td>
                  <Table.Td>{Object.keys(a.details).length > 0 && (
                    <Group gap={6} wrap="nowrap" align="flex-start">
                      <Code fz={11}>{JSON.stringify(a.details).slice(0, 160)}{JSON.stringify(a.details).length > 160 ? '…' : ''}</Code>
                      <Button size="compact-xs" variant="subtle" onClick={() => setOpen(a)}>All details</Button>
                    </Group>)}</Table.Td>
                </Table.Tr>
              ))}
              {rows.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" p="md">No audit events.</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Modal opened={open !== null} onClose={() => setOpen(null)} size="xl"
        title={open ? `${open.action} · ${fmtDate(open.timestamp)} · ${open.outcome}` : ''}>
        {open && (
          <>
            <Text size="xs" c="dimmed" mb="xs">{open.actor} · {open.target_type} {open.target_id}</Text>
            <Code block style={{ maxHeight: '65vh', overflow: 'auto' }}>{JSON.stringify(open.details, null, 2)}</Code>
          </>
        )}
      </Modal>
    </>
  );
}

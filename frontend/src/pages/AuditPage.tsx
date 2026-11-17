import { Card, Code, Group, Table, Text, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';

import { StateBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { fmtDate } from '../services/format';
import { useAudit } from '../hooks/queries';

export function AuditPage() {
  const audit = useAudit(undefined, 500);
  const [q, setQ] = useState('');
  const needle = q.trim().toLowerCase();
  const rows = (audit.data ?? []).filter((a) => !needle
    || [a.actor, a.action, a.target_type, a.target_id, a.outcome].some((v) => v.toLowerCase().includes(needle)));
  return (
    <>
      <PageHeader title="Logs & Audit Trail"
        description="Every significant action: who, what, which target, when and the outcome. Secrets are redacted before storage." />
      <Group mb="md"><TextInput placeholder="Filter by actor, action, target or outcome" leftSection={<IconSearch size={16} />}
        value={q} onChange={(e) => setQ(e.currentTarget.value)} w={360} aria-label="Filter audit events" /></Group>
      <QueryState isLoading={audit.isLoading} error={audit.error} />
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={820}>
          <Table verticalSpacing={6} horizontalSpacing="md" striped>
            <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>Actor</Table.Th><Table.Th>Action</Table.Th><Table.Th>Target</Table.Th><Table.Th>Outcome</Table.Th><Table.Th>Details</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {rows.map((a) => (
                <Table.Tr key={a.id}>
                  <Table.Td><Text size="sm">{fmtDate(a.timestamp)}</Text></Table.Td>
                  <Table.Td>{a.actor}</Table.Td>
                  <Table.Td><Text size="sm" ff="monospace">{a.action}</Text></Table.Td>
                  <Table.Td><Text size="sm">{a.target_type} <Text span c="dimmed" ff="monospace">{a.target_id.slice(0, 8)}</Text></Text></Table.Td>
                  <Table.Td><StateBadge state={a.outcome} /></Table.Td>
                  <Table.Td>{Object.keys(a.details).length > 0 && <Code fz={11}>{JSON.stringify(a.details).slice(0, 160)}</Code>}</Table.Td>
                </Table.Tr>
              ))}
              {rows.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" p="md">No audit events.</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </>
  );
}

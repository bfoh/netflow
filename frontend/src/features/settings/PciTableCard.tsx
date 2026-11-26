import { Badge, Button, Card, FileButton, Group, Stack, Text, TextInput, Title } from '@mantine/core';
import { IconFileImport } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import { normalSystem } from '../stage/zone';

/** Settings → Templates: the team's PCI table (D-114), imported once. */
export function PciTableCard() {
  const table = useQuery({ queryKey: ['pci-mapping'], queryFn: api.pciMapping });
  const load = useAction((file: File) => api.importPciMapping(file), (t) => `PCI table imported: ${t.systems} systems`,
    { errorInDialog: true });
  const [lookup, setLookup] = useState('');
  const system = normalSystem(lookup);
  const row = useQuery({ queryKey: ['pci-row', system], queryFn: () => api.pciRow(system!), enabled: !!system && !!table.data,
    retry: false });
  const t = table.data;
  return (
    <Card withBorder>
      <Group justify="space-between" mb={4}>
        <Title order={2}>PCI table (Flexi BBU cells)</Title>
        {t ? <Badge color="teal" variant="light" tt="none">{t.systems} systems</Badge> : <Badge color="gray" variant="light" tt="none">not imported</Badge>}
      </Group>
      <Hint>
        The team&apos;s PCI mapping workbook (.xlsx, or the same table saved as CSV). Each system&apos;s BBU cells take their PCIs from its
        row: cell 1 from “Compact Sector 1”, cell 2 from “Compact Sector 2”. Kept on this PC; importing a new one replaces it.
      </Hint>
      <Stack gap="xs" mt="xs">
        {t && <Text size="sm">{t.filename} · imported {t.imported_at ? fmtDate(t.imported_at) : ''} by {t.imported_by}</Text>}
        <Group gap="sm" align="flex-end">
          <FileButton onChange={(f) => f && load.mutate(f)} accept=".xlsx,.csv,text/csv">
            {(props) => <Button {...props} variant="light" leftSection={<IconFileImport size={16} />} loading={load.isPending}>
              {t ? 'Import a new table…' : 'Import the table…'}</Button>}
          </FileButton>
          {t && <TextInput label="Look up a system" w={160} placeholder="e.g. B007" value={lookup}
            onChange={(e) => setLookup(e.currentTarget.value)} />}
          {t && system && <Text size="sm" pb={6}>{row.data ? `${row.data.system}: ${row.data.pcis.filter((p) => p !== null).join(', ')}`
            : row.isError ? `${system} is not in the table` : '…'}</Text>}
        </Group>
        <DialogError error={load.error} />
      </Stack>
    </Card>
  );
}

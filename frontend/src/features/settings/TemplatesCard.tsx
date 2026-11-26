import { Badge, Button, Card, FileInput, Group, Modal, NumberInput, Stack, Table, Text, Title } from '@mantine/core';
import { IconFileImport } from '@tabler/icons-react';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { useConfirm } from '../../hooks/useConfirm';
import { useAction, useTemplates } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { ConfigTemplate, TemplateRole } from '../../types/api';
import { TEMPLATE_ROLES, zoneInName } from '../stage/zone';

const RULE_WORDS: Record<string, string> = {
  zone_tag: 'zone tag', ten_plus127: '10.(127+zone)', ten_zone: '10.zone', ten_zero_zone: '10.0.zone', onethirty_zone: '130.zone',
};

/** Import a team file as the template of a role, optionally checked against another zone's file. */
function ImportTemplate({ role, label, onClose }: { role: TemplateRole; label: string; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [zone, setZone] = useState<number | string>('');
  const [other, setOther] = useState<File | null>(null);
  const [otherZone, setOtherZone] = useState<number | string>('');
  const [done, setDone] = useState<{ template: ConfigTemplate; to_check: string[] } | null>(null);
  const base = role === 'fortigate_base';
  const run = useAction(async () => ({
    ...(await api.importTemplate({
      role, filename: file!.name, text: await file!.text(), zone: zone === '' ? null : Number(zone),
      ...(other ? { verify: { filename: other.name, text: await other.text(), zone: otherZone === '' ? null : Number(otherZone) } } : {}),
    })),
  }), 'Template kept', { errorInDialog: true });
  if (done) {
    const t = done.template;
    return (
      <Stack>
        <Text size="sm">Kept <b>{label} {t.version}</b>{t.reference_zone ? ` (from zone ${t.reference_zone})` : ''}.</Text>
        {t.verified_zone && <Badge color="teal" variant="light" tt="none">Gives the zone {t.verified_zone} file exactly</Badge>}
        {!base && <Text size="xs" c="dimmed">{Object.entries(t.counts).filter(([, n]) => n).map(([k, n]) => `${RULE_WORDS[k] ?? k} ×${n}`).join(' · ')}</Text>}
        {done.to_check.length > 0 && (
          <Stack gap={2}>
            <Text size="sm" fw={600} c="orange">Check these lines: they hold the zone&apos;s number in another form and were kept as they are</Text>
            {done.to_check.map((l) => <Text key={l} size="xs" ff="monospace">{l}</Text>)}
          </Stack>
        )}
        <Group justify="flex-end"><Button onClick={onClose}>Done</Button></Group>
      </Stack>
    );
  }
  return (
    <Stack>
      <FileInput label="The team's file" placeholder="Choose the file" value={file} onChange={(f) => { setFile(f); if (f && zone === '') setZone(zoneInName(f.name) ?? ''); }} clearable />
      {!base && (
        <>
          <NumberInput label="Zone of this file" description="Read from its name (z041 → 41) when it has one." min={1} max={128} value={zone} onChange={setZone} />
          <FileInput label="Same file for another zone (to check, optional)" description="UNDM keeps the template only if it gives this file exactly."
            placeholder="Choose the file" value={other} onChange={(f) => { setOther(f); if (f && otherZone === '') setOtherZone(zoneInName(f.name) ?? ''); }} clearable />
          {other && <NumberInput label="Its zone" min={1} max={128} value={otherZone} onChange={setOtherZone} />}
        </>
      )}
      <DialogError error={run.error} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>Back</Button>
        <Button disabled={!file} loading={run.isPending} leftSection={<IconFileImport size={16} />}
          onClick={() => run.mutate(undefined, { onSuccess: setDone })}>Import</Button>
      </Group>
    </Stack>
  );
}

/** Settings → For all systems: the team's files as templates, one per role (D-111). */
export function TemplatesCard() {
  const templates = useTemplates();
  const [importing, setImporting] = useState<TemplateRole | null>(null);
  const del = useAction((id: string) => api.deleteTemplate(id), 'Template removed');
  const [ask, confirmDialog] = useConfirm();
  const byRole = new Map((templates.data ?? []).map((t) => [t.role, t]));
  const label = (r: TemplateRole) => TEMPLATE_ROLES.find((x) => x.role === r)?.label ?? r;
  return (
    <Card withBorder>
      {confirmDialog}
      <Title order={2} size="h5" mb={4}>Configuration templates</Title>
      <Hint>
        The team&apos;s files, kept on this PC (never in UNDM&apos;s code). From them UNDM makes every system&apos;s files for its zone:
        the zone tag (z041), 10.(127+zone).x, 10.zone.x, 10.0.zone.x and 130.zone.x change; everything else is copied as it is.
        Import a new version when the team releases one.
      </Hint>
      <Table.ScrollContainer minWidth={560}>
        <Table verticalSpacing="xs" mt="sm">
          <Table.Thead><Table.Tr><Table.Th>File</Table.Th><Table.Th>Version</Table.Th><Table.Th>Checked</Table.Th><Table.Th>Imported</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {TEMPLATE_ROLES.map(({ role, label: name }) => {
              const t = byRole.get(role);
              return (
                <Table.Tr key={role}>
                  <Table.Td><Text size="sm">{name}</Text></Table.Td>
                  <Table.Td>{t ? <Text size="sm">{t.version || '—'}{t.reference_zone ? ` · from zone ${t.reference_zone}` : ''}</Text> : <Text size="sm" c="dimmed">not imported</Text>}</Table.Td>
                  <Table.Td>{!t ? null : role === 'fortigate_base' ? <Text size="xs" c="dimmed">same for every zone</Text>
                    : t.verified_zone ? <Badge color="teal" variant="light" tt="none">against zone {t.verified_zone}</Badge>
                      : <Badge color="gray" variant="light" tt="none">not checked</Badge>}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{t ? `${fmtDate(t.created_at)} · ${t.created_by}` : ''}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Button size="compact-xs" variant="light" onClick={() => setImporting(role)}>{t ? 'Import a new version…' : 'Import…'}</Button>
                      {t && <Button size="compact-xs" variant="subtle" color="red" aria-label={`Remove ${name}`}
                        onClick={() => ask({ title: `Remove the ${name} template?`, confirmLabel: 'Remove',
                          message: 'Systems already generated keep their files. Generating needs a template again.',
                          onConfirm: () => del.mutateAsync(t.id) })}>Remove</Button>}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Modal opened={!!importing} onClose={() => setImporting(null)} title={importing ? `Import: ${label(importing)}` : ''} size="lg">
        {importing && <ImportTemplate key={importing} role={importing} label={label(importing)} onClose={() => setImporting(null)} />}
      </Modal>
    </Card>
  );
}

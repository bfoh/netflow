import { Badge, Button, Card, FileInput, Group, Modal, NumberInput, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { IconDownload, IconFileImport } from '@tabler/icons-react';
import { useRef, useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Notice } from '../../components/Notice';
import { Hint } from '../../components/Hint';
import { useConfirm } from '../../hooks/useConfirm';
import { useAction, useTemplates } from '../../hooks/queries';
import { api, ApiError } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { ConfigTemplate, TemplateRole } from '../../types/api';
import { type FileFacts, formatWords, normalSystem, readFileFacts, TEMPLATE_ROLES } from '../stage/zone';

const RULE_WORDS: Record<string, string> = {
  zone_tag: 'zone tag', ten_plus127: '10.(127+zone)', ten_zone: '10.zone', ten_zero_zone: '10.0.zone', onethirty_zone: '130.zone',
  zone3: 'Z/Zone + zone', tac: 'tac', system: 'system', pci: 'cell PCIs', secret: 'password slot',
  accepted_differences: 'accepted differences',
};
const systemRole = (r: TemplateRole) => !!TEMPLATE_ROLES.find((x) => x.role === r)?.system;
const secretRole = (r: TemplateRole) => !!TEMPLATE_ROLES.find((x) => x.role === r)?.secret;
type Done = { template: ConfigTemplate; to_check: string[]; verified_bytes: boolean | null; accepted: string[] };
const FROM = { name: 'Read from its name.', text: 'Read from the file (its name does not say).' } as const;

/** A zone and a system read from a chosen file: filled in unless the person typed their own. */
function useFileFields(bySystem: boolean) {
  const [zone, setZone] = useState<number | string>('');
  const [system, setSystem] = useState('');
  const [facts, setFacts] = useState<FileFacts | null>(null);
  const [typed, setTyped] = useState({ zone: false, system: false });
  const seq = useRef(0);
  const read = async (f: File | null) => {
    const n = ++seq.current;
    if (!f) { setFacts(null); return; }
    const got = await readFileFacts(f);
    if (n !== seq.current) return; // another file was chosen meanwhile
    setFacts(got);
    if (!typed.zone) setZone(got.zone ?? '');
    if (bySystem && !typed.system) setSystem(got.system ?? '');
  };
  return {
    zone, system, read,
    setZone: (v: number | string) => { setZone(v); setTyped((t) => ({ ...t, zone: v !== '' })); },
    setSystem: (v: string) => { setSystem(v); setTyped((t) => ({ ...t, system: v.trim() !== '' })); },
    zoneFrom: !typed.zone && facts?.zoneFrom && zone !== '' ? FROM[facts.zoneFrom] : undefined,
    systemFrom: bySystem && !typed.system && facts?.systemFrom && system ? FROM[facts.systemFrom] : undefined,
    disagree: (facts?.disagree ?? []).filter((d) => bySystem || d.includes('zone')),
  };
}

function Disagree({ items }: { items: string[] }) {
  return items.length ? <Text size="xs" c="orange">Check this file: {items.join('; ')}.</Text> : null;
}

/** Import a team file as the template of a role, optionally checked against another zone's file. */
function ImportTemplate({ role, label, onClose }: { role: TemplateRole; label: string; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [other, setOther] = useState<File | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const base = role === 'fortigate_base';
  const bySystem = systemRole(role);
  const mine = useFileFields(bySystem);
  const its = useFileFields(bySystem);
  const { zone, system } = mine;
  const { zone: otherZone, system: otherSystem } = its;
  const run = useAction(async (accept: boolean) => ({
    ...(await api.importTemplate({
      role, filename: file!.name, text: await file!.text(), zone: zone === '' ? null : Number(zone),
      ...(bySystem && system.trim() ? { system: normalSystem(system) ?? system } : {}),
      ...(other ? { verify: { filename: other.name, text: await other.text(), zone: otherZone === '' ? null : Number(otherZone),
        ...(bySystem && otherSystem.trim() ? { system: normalSystem(otherSystem) ?? otherSystem } : {}) } } : {}),
      ...(accept ? { accept_differences: true } : {}),
    })),
  }), 'Template kept', { errorInDialog: true });
  // The second file differs in some lines: shown, and kept only if the person says so (D-114).
  const differences = run.error instanceof ApiError && run.error.status === 409 && Array.isArray(run.error.details)
    ? (run.error.details as string[]) : null;
  if (done) {
    const t = done.template;
    return (
      <Stack>
        <Text size="sm">Kept <b>{label} {t.version}</b>{t.reference_zone ? ` (from zone ${t.reference_zone}${t.reference_system ? `, ${t.reference_system}` : ''})` : ''}.</Text>
        {t.verified_zone && (
          <Group gap="xs">
            <Badge color="teal" variant="light" tt="none">
              {done.accepted.length ? 'Gives' : 'Gives exactly'} the zone {t.verified_zone}{t.verified_system ? `, ${t.verified_system}` : ''} file
              {done.accepted.length ? ` except ${done.accepted.length} accepted line(s)` : ''}</Badge>
            {done.verified_bytes === true && <Badge color="teal" variant="light" tt="none">byte for byte</Badge>}
            {done.verified_bytes === false && <Text size="xs" c="dimmed">line for line; that file&apos;s line endings differ from this one&apos;s</Text>}
          </Group>
        )}
        <Text size="xs" c="dimmed">Kept as written: {formatWords(t)}.</Text>
        {!base && <Text size="xs" c="dimmed">{Object.entries(t.counts).filter(([, n]) => n).map(([k, n]) => `${RULE_WORDS[k] ?? k} ×${n}`).join(' · ')}</Text>}
        {done.accepted.length > 0 && (
          <Stack gap={2}>
            <Text size="sm" fw={600}>Accepted: these lines of the second file differ</Text>
            {done.accepted.map((l) => <Text key={l} size="xs" ff="monospace">{l}</Text>)}
          </Stack>
        )}
        {secretRole(role) && <Text size="xs" c="dimmed">The admin password was left out of the template: a file handed out gets the password of the modem&apos;s login.</Text>}
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
      <FileInput label="The team's file" placeholder="Choose the file" value={file} onChange={(f) => { setFile(f); if (!base) void mine.read(f); }} clearable />
      {!base && (
        <>
          <Group grow align="flex-start">
            <NumberInput label="Zone of this file" description={mine.zoneFrom ?? 'Read from its name or text when it has one (z041 → 41).'}
              min={1} max={128} value={zone} onChange={mine.setZone} />
            {bySystem && <TextInput label="System of this file" description={mine.systemFrom ?? 'Read from its name or text when it has one (e.g. B007).'}
              value={system} onChange={(e) => mine.setSystem(e.currentTarget.value)} placeholder="e.g. B007" />}
          </Group>
          <Disagree items={mine.disagree} />
          <FileInput label={bySystem ? 'Same file for another system and zone (to check, optional)' : 'Same file for another zone (to check, optional)'}
            description="UNDM keeps the template only if it gives this file exactly (or you accept the differences it shows)."
            placeholder="Choose the file" value={other} onChange={(f) => { setOther(f); void its.read(f); }} clearable />
          {other && (
            <>
              <Group grow align="flex-start">
                <NumberInput label="Its zone" description={its.zoneFrom} min={1} max={128} value={otherZone} onChange={its.setZone} />
                {bySystem && <TextInput label="Its system" description={its.systemFrom} value={otherSystem}
                  onChange={(e) => its.setSystem(e.currentTarget.value)} placeholder="e.g. B009" />}
              </Group>
              <Disagree items={its.disagree} />
            </>
          )}
        </>
      )}
      {differences ? (
        <Notice kind="caution" title={run.error!.message}>
          {differences.map((d) => <Text key={d} size="xs" ff="monospace">{d}</Text>)}
          <Text size="xs" mt={4}>If these lines differ on purpose (for example a site label written by hand), keep the template anyway:
            generated files then follow the template in these lines.</Text>
        </Notice>
      ) : <DialogError error={run.error} />}
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>Back</Button>
        {differences && <Button variant="light" color="orange" loading={run.isPending}
          onClick={() => run.mutate(true, { onSuccess: setDone })}>Keep it anyway</Button>}
        <Button disabled={!file} loading={run.isPending} leftSection={<IconFileImport size={16} />}
          onClick={() => run.mutate(false, { onSuccess: setDone })}>Import</Button>
      </Group>
    </Stack>
  );
}

/** Settings → For all systems: the team's files as templates, one per role (D-111). */
export function TemplatesCard() {
  const templates = useTemplates();
  const [importing, setImporting] = useState<TemplateRole | null>(null);
  const del = useAction((id: string) => api.deleteTemplate(id), 'Template removed');
  const [zone, setZone] = useState<number | string>('');
  const [sysText, setSysText] = useState('');
  const z = typeof zone === 'number' && zone >= 1 && zone <= 128 ? zone : null;
  const sys = sysText.trim() ? normalSystem(sysText) ?? null : null;
  const [skipped, setSkipped] = useState<string[] | null>(null);
  const one = useAction((r: TemplateRole) => api.downloadTemplateFile(r, r === 'fortigate_base' ? null : z, systemRole(r) ? sys : null),
    (n) => `Downloaded ${n}`);
  const all = useAction(() => api.downloadTemplateFiles(z!, sys), (r) => `Downloaded ${r.name}`);
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
        The modem&apos;s and the BBU&apos;s files also follow the system (B007, MRBTS-7), and the BBU&apos;s cells take their PCIs from
        the PCI table below. Import a new version when the team releases one. Downloads are byte for byte as the team writes each file.
      </Hint>
      <Group align="flex-end" gap="sm" mt="xs">
        <NumberInput label="Download for zone" w={150} min={1} max={128} value={zone} onChange={setZone} />
        <TextInput label="and system" w={130} value={sysText} onChange={(e) => setSysText(e.currentTarget.value)} placeholder="e.g. B007"
          error={sysText.trim() && !sys ? 'e.g. B007' : undefined} />
        <Button variant="default" leftSection={<IconDownload size={16} />} disabled={!z || byRole.size === 0}
          loading={all.isPending} onClick={() => all.mutate(undefined, { onSuccess: (r) => setSkipped(r.skipped) })}>
          All files for zone {z ?? '…'}{sys ? ` · ${sys}` : ''}</Button>
      </Group>
      {skipped && skipped.length > 0 && (
        <Notice kind="settled" compact mt="xs" title="Not in the download">{skipped.map((x) => <div key={x}>{x}</div>)}</Notice>
      )}
      <Table.ScrollContainer minWidth={560}>
        <Table verticalSpacing="xs" mt="sm">
          <Table.Thead><Table.Tr><Table.Th>File</Table.Th><Table.Th>Version</Table.Th><Table.Th>Checked</Table.Th><Table.Th>Imported</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {TEMPLATE_ROLES.map(({ role, label: name }) => {
              const t = byRole.get(role);
              return (
                <Table.Tr key={role}>
                  <Table.Td><Text size="sm">{name}</Text></Table.Td>
                  <Table.Td>{t ? <><Text size="sm">{t.version || '—'}{t.reference_zone ? ` · from zone ${t.reference_zone}` : ''}{t.reference_system ? ` · ${t.reference_system}` : ''}</Text>
                    <Text size="xs" c="dimmed">{formatWords(t)}</Text></> : <Text size="sm" c="dimmed">not imported</Text>}</Table.Td>
                  <Table.Td>{!t ? null : role === 'fortigate_base' ? <Text size="xs" c="dimmed">same for every zone</Text>
                    : t.verified_zone ? <Badge color="teal" variant="light" tt="none">against zone {t.verified_zone}{t.verified_system ? ` · ${t.verified_system}` : ''}
                      {t.counts.accepted_differences ? ` (${t.counts.accepted_differences} accepted)` : ''}</Badge>
                      : <Badge color="gray" variant="light" tt="none">not checked</Badge>}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{t ? `${fmtDate(t.created_at)} · ${t.created_by}` : ''}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      {t && secretRole(role) && <Text size="xs" c="dimmed">download from Stage a system</Text>}
                      {t && !secretRole(role) && <Button size="compact-xs" variant="subtle" aria-label={`Download ${name}`} leftSection={<IconDownload size={14} />}
                        disabled={(role !== 'fortigate_base' && !z) || (systemRole(role) && !sys)} loading={one.isPending && one.variables === role}
                        onClick={() => one.mutate(role)}>{role === 'fortigate_base' ? 'Download' : `Zone ${z ?? '…'}${systemRole(role) ? ` · ${sys ?? '…'}` : ''}`}</Button>}
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

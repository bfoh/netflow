import { Anchor, Badge, Button, Card, Group, NumberInput, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { Beside, FieldRow } from '../../components/FieldRow';
import { Tag } from '../../components/Badges';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { IconDownload, IconFileCode, IconScale } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { InlineStatus } from '../../components/InlineStatus';
import { Notice } from '../../components/Notice';
import { useConfirm } from '../../hooks/useConfirm';
import { useAction, useTemplates } from '../../hooks/queries';
import { api } from '../../services/api';
import type { ComparedFile, Device, Project, TemplateRole } from '../../types/api';
import { type Choice, type Choices, EMPTY_CHOICE } from './choices';
import type { Role, RoleKey } from './roles';
import { normalSystem, systemInName, TEMPLATE_ROLES, zoneInName, zoneWords } from './zone';
import { paths } from '../../paths';

/** Step 1: the system's zone (D-111) and system (D-114), prefilled from its name (B007z045 → B007, 45). */
export function ZoneField({ project }: { project: Project }) {
  const guess = zoneInName(project.name);
  const sysGuess = systemInName(project.name);
  const [value, setValue] = useState<number | string>(project.zone ?? guess ?? '');
  const [sysText, setSysText] = useState(project.system_id ?? sysGuess ?? '');
  const qc = useQueryClient();
  // Saved by themselves (D-121): what is shown is what the system has, never only typed.
  const save = useAction((body: { zone: number | null; system_id: string | null }) => api.updateProject(project.id, body),
    undefined, { errorInDialog: true });
  const zone = typeof value === 'number' ? value : undefined;
  const system = sysText.trim() ? normalSystem(sysText) : null;
  const zoneOk = zone === undefined || (zone >= 1 && zone <= 128);
  const changed = (zone ?? null) !== (project.zone ?? null) || (system ?? null) !== (project.system_id ?? null);
  const ready = changed && zoneOk && system !== undefined;
  const body = { zone: zone ?? null, system_id: system ?? null };
  const unsaved = useRef<typeof body | null>(null);
  unsaved.current = ready ? body : null;
  useEffect(() => {
    if (!ready) return;
    const t = window.setTimeout(() => save.mutate(body), 600);
    return () => window.clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, body.zone, body.system_id]);
  // Leaving step 1 before the pause ends still saves what was typed.
  useEffect(() => () => {
    if (unsaved.current) void api.updateProject(project.id, unsaved.current).then(() => qc.invalidateQueries());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const pcis = useQuery({ queryKey: ['pci-row', system], queryFn: () => api.pciRow(system!), enabled: !!system, retry: false });
  return (
    <Card>
      <FieldRow gap="sm">
        <NumberInput label="Zone" w={120} min={1} max={128} value={value} onChange={setValue}
          error={zoneOk ? undefined : '1 to 128'}
          description={!project.zone && guess ? `From the name: ${guess}` : undefined} />
        <TextInput label="System" w={140} value={sysText} onChange={(e) => setSysText(e.currentTarget.value)}
          placeholder="e.g. B007" error={sysText.trim() && !system ? 'A B system, e.g. B007' : undefined}
          description={!project.system_id && sysGuess ? `From the name: ${sysGuess}` : undefined} />
        <Beside role="status">
          {save.isPending || ready
            ? <InlineStatus tone="neutral">Saving…</InlineStatus>
            : save.error ? <InlineStatus tone="danger">Not saved: {save.error.message}</InlineStatus>
              : (project.zone || project.system_id) && <InlineStatus tone="success">Saved</InlineStatus>}
        </Beside>
        {zone && zoneOk && <Beside><Text size="sm" c="dimmed">{zoneWords(zone)}</Text></Beside>}
      </FieldRow>
      {system && (
        <Text size="xs" c="dimmed" mt={4}>
          {system} · MRBTS-{Number(system.slice(1))} · {pcis.data ? `cell PCIs ${pcis.data.pcis.filter((p) => p !== null).join(', ')} (PCI table)`
            : pcis.isError ? 'not in the PCI table (Settings → Templates)' : '…'}
        </Text>
      )}
      <Text size="xs" c="dimmed" mt={4}>The devices&apos; files are generated for this zone (and the modem&apos;s and BBU&apos;s for this system) in step 2, from the templates in Settings → Templates.</Text>
    </Card>
  );
}

/** Step 2: generate every device's files from the team's templates, or compare them with the files already there. */
export function GeneratePanel({ project, roles, choices, onReplace }: {
  project: Project; roles: { role: Role; device: Device }[]; choices: Choices; onReplace: (next: Choices) => void;
}) {
  const templates = useTemplates();
  const have = new Set((templates.data ?? []).map((t) => t.role));
  const byRole = new Map(roles.map(({ role, device }) => [role.key, device]));
  const wanted = TEMPLATE_ROLES.filter((t) => t.wizardRole && byRole.has(t.wizardRole));
  const ready = wanted.filter((t) => have.has(t.role));
  const assignments = Object.fromEntries(ready.map((t) => [t.role, byRole.get(t.wizardRole!)!.id])) as Partial<Record<TemplateRole, string>>;
  const needsSystem = ready.some((t) => t.system) && !project.system_id;
  const bbu = have.has('bbu_scf');
  const [skipped, setSkipped] = useState<string[] | null>(null);
  const [compared, setCompared] = useState<ComparedFile[] | null>(null);
  const [ask, confirmDialog] = useConfirm();
  const generate = useAction(() => api.generateFiles(project.id, assignments),
    (r) => `${r.length} files made for zone ${project.zone}`, { errorInDialog: true });
  const compare = useAction(() => api.compareFiles(project.id, assignments), undefined, { errorInDialog: true });
  const save = useAction(() => api.downloadSystemFiles(project.id, assignments), (r) => `Downloaded ${r.name}`, { errorInDialog: true });
  const apply = (made: { role: TemplateRole; version_id: string }[]) => {
    const next: Choices = { ...choices };
    for (const m of made) {
      const t = TEMPLATE_ROLES.find((x) => x.role === m.role)!;
      const key = t.wizardRole as RoleKey;
      next[key] = { ...(next[key] ?? EMPTY_CHOICE), [t.slot]: m.version_id } as Choice;
    }
    onReplace(next);
  };
  const run = () => generate.mutate(undefined, { onSuccess: apply });
  const chosen = ready.some((t) => (choices[t.wizardRole!] as Choice | undefined)?.[t.slot]);
  const name = (r: TemplateRole) => TEMPLATE_ROLES.find((x) => x.role === r)?.label ?? r;
  if (wanted.length === 0 && !bbu) return null;
  return (
    <Card withBorder>
      {confirmDialog}
      <Group justify="space-between" mb={4} wrap="wrap">
        <Title order={3}>Files from the team&apos;s templates</Title>
        {project.zone ? <Badge variant="light" tt="none">zone {project.zone}</Badge> : null}
      </Group>
      {!project.zone ? (
        <Text size="sm">Set the system&apos;s zone in step 1 first.</Text>
      ) : needsSystem ? (
        <Text size="sm">Set the system (e.g. B007) in step 1 first: the modem&apos;s and the BBU&apos;s files depend on it.</Text>
      ) : ready.length === 0 && !bbu ? (
        <Text size="sm">No templates yet: import the team&apos;s files once in <Anchor component={Link} to={paths.settings('templates')} size="sm">Settings → Templates</Anchor>. Files can still be imported by hand below.</Text>
      ) : (
        <Stack gap="xs">
          <Text size="sm">Makes {ready.length} {ready.length === 1 ? 'file' : 'files'} for zone {project.zone} and chooses them below.
            {ready.length < wanted.length && <> No template for: {wanted.filter((t) => !have.has(t.role)).map((t) => t.label).join(', ')} (import those files by hand).</>}</Text>
          <Group gap="xs">
            <Button leftSection={<IconFileCode size={16} />} loading={generate.isPending}
              onClick={() => (chosen ? ask({ title: 'Replace the files chosen below?', confirmLabel: 'Generate and choose them',
                message: `The files made for zone ${project.zone} replace the files chosen now. The earlier files stay on the devices.`,
                onConfirm: async () => run() }) : run())}>Generate the files for zone {project.zone}</Button>
            <Button variant="default" leftSection={<IconScale size={16} />} loading={compare.isPending}
              onClick={() => compare.mutate(undefined, { onSuccess: setCompared })}>Compare with the devices&apos; files</Button>
            <Button variant="default" leftSection={<IconDownload size={16} />} loading={save.isPending}
              onClick={() => save.mutate(undefined, { onSuccess: (r) => setSkipped(r.skipped) })}>
              Download the files for zone {project.zone}{project.system_id ? ` · ${project.system_id}` : ''}</Button>
          </Group>
          <Text size="xs" c="dimmed">The download is byte for byte as the team writes the files (their line endings and last line).
            {bbu && ' It includes the Flexi BBU’s SCF, with its cells’ PCIs from the PCI table.'}
            {ready.some((t) => t.secret) && ' The modem’s file gets its admin password from the modem’s login.'}</Text>
          {skipped && skipped.length > 0 && (
            <Notice kind="caution" compact title="Not in the download">
              {skipped.map((s) => <div key={s}>{s}</div>)}
            </Notice>
          )}
          <DialogError error={generate.error ?? compare.error ?? save.error} />
          {compared && (
            <Table.ScrollContainer minWidth={520}>
              <Table verticalSpacing={4} aria-label="Comparison with the devices' files">
                <Table.Thead><Table.Tr><Table.Th>Template</Table.Th><Table.Th>Device&apos;s file</Table.Th><Table.Th>Result</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {compared.map((c) => (
                    <Table.Tr key={c.role}>
                      <Table.Td><Text size="sm">{name(c.role)}</Text><Text size="xs" c="dimmed">{c.generated_name}</Text></Table.Td>
                      <Table.Td><Text size="sm">{c.file_name ?? '—'}</Text></Table.Td>
                      <Table.Td>
                        {!c.file_name ? <Text size="sm" c="dimmed">no file on the device to compare</Text>
                          : c.same ? <Tag tone="success">identical · {c.lines} lines</Tag>
                            : <Stack gap={2}>
                              <Tag tone="danger">differs</Tag>
                              {c.differences.map(([n, a, b]) => (
                                <Text key={n} size="xs" ff="monospace">line {n}: template “{a}” · file “{b}”</Text>))}
                            </Stack>}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
          {compared && <Text size="xs" c="dimmed">Compared line by line: line endings are not compared (the devices get the same lines either way).</Text>}
        </Stack>
      )}
    </Card>
  );
}

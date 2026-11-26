import { Anchor, Badge, Button, Card, Group, NumberInput, Stack, Table, Text, Title } from '@mantine/core';
import { IconFileCode, IconScale } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { useConfirm } from '../../hooks/useConfirm';
import { useAction, useTemplates } from '../../hooks/queries';
import { api } from '../../services/api';
import type { ComparedFile, Device, Project, TemplateRole } from '../../types/api';
import { type Choice, type Choices, EMPTY_CHOICE } from './choices';
import type { Role, RoleKey } from './roles';
import { TEMPLATE_ROLES, zoneInName, zoneWords } from './zone';

/** Step 1: the system's zone (D-111), prefilled from its name (B001z045 → 45). */
export function ZoneField({ project }: { project: Project }) {
  const guess = zoneInName(project.name);
  const [value, setValue] = useState<number | string>(project.zone ?? guess ?? '');
  const save = useAction((z: number | null) => api.updateProject(project.id, { zone: z }), 'Zone saved');
  const zone = typeof value === 'number' ? value : undefined;
  const changed = (zone ?? null) !== (project.zone ?? null);
  return (
    <Card withBorder>
      <Group align="flex-end" gap="sm" wrap="wrap">
        <NumberInput label="Zone" w={120} min={1} max={128} value={value} onChange={setValue}
          description={!project.zone && guess ? `From the name: ${guess}` : undefined} />
        <Button variant={changed ? 'filled' : 'default'} disabled={!changed || (zone !== undefined && (zone < 1 || zone > 128))}
          loading={save.isPending} onClick={() => save.mutate(zone ?? null)}>Save zone</Button>
        {zone && zone >= 1 && zone <= 128 && <Text size="sm" c="dimmed" pb={6}>{zoneWords(zone)}</Text>}
      </Group>
      <Text size="xs" c="dimmed" mt={4}>The devices&apos; files are generated for this zone in step 2, from the templates in Settings → For all systems.</Text>
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
  const wanted = TEMPLATE_ROLES.filter((t) => byRole.has(t.wizardRole));
  const ready = wanted.filter((t) => have.has(t.role));
  const assignments = Object.fromEntries(ready.map((t) => [t.role, byRole.get(t.wizardRole)!.id])) as Partial<Record<TemplateRole, string>>;
  const [compared, setCompared] = useState<ComparedFile[] | null>(null);
  const [ask, confirmDialog] = useConfirm();
  const generate = useAction(() => api.generateFiles(project.id, assignments),
    (r) => `${r.length} files made for zone ${project.zone}`, { errorInDialog: true });
  const compare = useAction(() => api.compareFiles(project.id, assignments), undefined, { errorInDialog: true });
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
  const chosen = ready.some((t) => (choices[t.wizardRole] as Choice | undefined)?.[t.slot]);
  const name = (r: TemplateRole) => TEMPLATE_ROLES.find((x) => x.role === r)?.label ?? r;
  if (wanted.length === 0) return null;
  return (
    <Card withBorder>
      {confirmDialog}
      <Group justify="space-between" mb={4} wrap="wrap">
        <Title order={3} size="h5">Files from the team&apos;s templates</Title>
        {project.zone ? <Badge variant="light" tt="none">zone {project.zone}</Badge> : null}
      </Group>
      {!project.zone ? (
        <Text size="sm">Set the system&apos;s zone in step 1 first.</Text>
      ) : ready.length === 0 ? (
        <Text size="sm">No templates yet: import the team&apos;s files once in <Anchor component={Link} to="/settings?tab=shared" size="sm">Settings → For all systems</Anchor>. Files can still be imported by hand below.</Text>
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
          </Group>
          <DialogError error={generate.error ?? compare.error} />
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
                          : c.same ? <Badge color="teal" variant="light" tt="none">identical · {c.lines} lines</Badge>
                            : <Stack gap={2}>
                              <Badge color="red" variant="light" tt="none">differs</Badge>
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
        </Stack>
      )}
    </Card>
  );
}

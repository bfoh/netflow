import { Anchor, Badge, Button, Card, Code, Group, Stack, Text, Textarea, ThemeIcon, Title } from '@mantine/core';
import { IconCheck, IconDownload, IconExternalLink, IconPlugConnected } from '@tabler/icons-react';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { useAction, useConfigs, useFirmwareImages, useGuided } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { Device, GuidedStepState } from '../../types/api';
import { type Choice, planSteps } from './choices';
import type { Role } from './roles';

const short = (sha: string | null) => (sha ? `${sha.slice(0, 12)}…` : '');

/** A device staged by a person in its own portal (the Flexi BBU, D-117): UNDM checks the portal
 *  answers, hands out the files and records each step. It never logs in to the device. */
export function GuidedRun({ role, device, choice }: { role: Role; device: Device; choice: Choice }) {
  const guided = useGuided(device.id);
  const images = useFirmwareImages();
  const configs = useConfigs(device.id);
  const image = images.data?.find((i) => i.id === choice.imageId);
  const scf = configs.data?.find((v) => v.id === choice.fileId);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const done = useAction((step: string) => api.guidedDone(device.id, step, {
    note: notes[step] ?? '', image_id: choice.imageId, version_id: choice.fileId,
  }), (g) => `${device.name}: ${g.steps.filter((s) => s.done_by).length} of ${g.steps.length} steps recorded`, { errorInDialog: true });
  const undo = useAction((step: string) => api.guidedUndo(device.id, step), 'Step cleared');
  const steps = guided.data?.steps ?? [];
  const next = steps.find((s) => !s.done_by);
  const { missing } = planSteps(role, choice, device);
  const real = device.environment !== 'simulated';

  const what = (s: GuidedStepState) => {
    if (s.kind === 'software') {
      return image ? (
        <Stack gap={2}>
          <Text size="sm">{image.filename} · {image.version}</Text>
          <Text size="xs">SHA-256 <Code>{image.sha256}</Code></Text>
          <Anchor size="xs" href={api.firmwareFileUrl(image.id)}><IconDownload size={12} /> Download it from UNDM</Anchor>
        </Stack>
      ) : <Text size="sm" c="orange">Choose the software package in step 2.</Text>;
    }
    if (s.kind === 'file') {
      return scf ? (
        <Stack gap={2}>
          <Text size="sm">{scf.reference}</Text>
          <Anchor size="xs" href={api.guidedFileUrl(device.id, scf.id)}><IconDownload size={12} /> Download the SCF (as the team writes it)</Anchor>
        </Stack>
      ) : <Text size="sm" c="orange">Generate or choose the SCF in step 2.</Text>;
    }
    return null;
  };

  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <div>
          <Title order={3} size="h5">{device.name}</Title>
          <Text size="xs" c="dimmed">{role.title} · {device.management_address} · by hand in its portal</Text>
        </div>
        {steps.length > 0 && !next && <Badge color="teal" variant="filled" tt="none">Staged</Badge>}
      </Group>
      <Stack gap="xs">
        {real && device.management_address && (
          <Group gap="xs">
            <Button size="xs" variant="light" component="a" href={`https://${device.management_address}`} target="_blank" rel="noreferrer"
              rightSection={<IconExternalLink size={12} />}>Open its portal</Button>
            <Text size="xs" c="dimmed">UNDM never logs in to it: you log in and work in the portal; UNDM records each step.</Text>
          </Group>
        )}
        {missing.length > 0 && <Text size="xs" c="orange">Still needed: {missing.join(', ')} (step 2).</Text>}
        {steps.map((s, i) => (
          <Stack key={s.key} gap={4} pl="xs" style={{ borderLeft: `3px solid var(--mantine-color-${s.done_by ? 'teal' : s === next ? 'blue' : 'gray'}-4)` }}>
            <Group gap="xs" wrap="nowrap">
              {s.done_by && <ThemeIcon size="sm" color="teal" variant="light"><IconCheck size={12} /></ThemeIcon>}
              <Text size="sm" fw={s === next ? 600 : 400} c={!s.done_by && s !== next ? 'dimmed' : undefined}>{i + 1}. {s.title}</Text>
            </Group>
            {s.done_by ? (
              <Stack gap={2}>
                <Text size="xs" c="dimmed">By {s.done_by}{s.done_at ? `, ${fmtDate(s.done_at)}` : ''}{s.note ? ` · ${s.note}` : ''}</Text>
                {s.file_name && <Text size="xs" c="dimmed">{s.file_name} · SHA-256 <span title={s.file_sha256 ?? ''}>{short(s.file_sha256)}</span></Text>}
                <Group><Button size="compact-xs" variant="subtle" color="gray" loading={undo.isPending && undo.variables === s.key}
                  onClick={() => undo.mutate(s.key)}>Undo (and the steps after it)</Button></Group>
              </Stack>
            ) : s === next ? (
              <Stack gap={6}>
                <Text size="xs">{s.detail}</Text>
                {what(s)}
                {s.note_label && <Textarea size="xs" label={s.note_label} autosize minRows={1} maw={520}
                  value={notes[s.key] ?? ''} onChange={(e) => { const v = e.currentTarget.value; setNotes((n) => ({ ...n, [s.key]: v })); }} />}
                <Group>
                  <Button size="xs" loading={done.isPending} leftSection={s.kind === 'check' ? <IconPlugConnected size={14} /> : <IconCheck size={14} />}
                    disabled={(s.kind === 'software' && !image) || (s.kind === 'file' && !scf) || (!!s.note_label && (notes[s.key] ?? '').trim().length < 3)}
                    onClick={() => done.mutate(s.key)}>{s.kind === 'check' ? 'Check now' : 'Done'}</Button>
                </Group>
              </Stack>
            ) : null}
          </Stack>
        ))}
        <DialogError error={done.error ?? undo.error} />
      </Stack>
    </Card>
  );
}

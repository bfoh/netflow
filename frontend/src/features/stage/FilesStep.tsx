import { Alert, Badge, Button, Card, Checkbox, FileButton, Group, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconUpload } from '@tabler/icons-react';

import { useAction, useConfig, useConfigs, useCredentialRefs, useFirmwareImages } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { Device } from '../../types/api';
import { type Choice, EMPTY_CHOICE, planSteps } from './choices';
import type { Role } from './roles';

/** Choose one of the device's imported files, or import one; shows what UNDM found in it. */
function FilePick({ device, label, description, value, onChange, secrets, onSecrets, logins }: {
  device: Device; label: string; description: string; value: string | null; onChange: (id: string | null) => void;
  secrets?: Record<string, string>; onSecrets?: (s: Record<string, string>) => void; logins: { value: string; label: string }[];
}) {
  const configs = useConfigs(device.id);
  const chosen = useConfig(value);
  const imp = useAction(async (f: File) => api.importConfig(device.id, f.name, await f.text()), 'File imported and checked');
  const files = (configs.data ?? []).filter((v) => v.kind === 'imported');
  const report = chosen.data?.inspection;
  return (
    <Stack gap={4}>
      <Group align="flex-end" gap="xs" wrap="wrap">
        <Select label={label} description={description} placeholder={files.length ? 'Choose the file' : 'Import it first'}
          data={files.map((v) => ({ value: v.id, label: `${v.reference || 'file'} · ${fmtDate(v.created_at)}` }))}
          value={value} onChange={onChange} clearable w="100%" maw={420} />
        <FileButton onChange={(f) => { if (f) imp.mutate(f, { onSuccess: (v) => onChange(v.id) }); }}>
          {(props) => <Button {...props} variant="light" leftSection={<IconUpload size={14} />} loading={imp.isPending}>Import a file…</Button>}
        </FileButton>
      </Group>
      {report && (
        <Text size="xs" c={report.problems.length || report.blocked_reason ? 'red' : 'dimmed'}>
          {report.summary}{report.blocked_reason ? `. ${report.blocked_reason}` : ''}{report.problems.length ? `. ${report.problems.join('; ')}` : ''}
        </Text>
      )}
      {secrets && onSecrets && (report?.secret_slots ?? []).map((slot) => (
        <Select key={slot.slot_id} size="xs" w="100%" maw={420} clearable label={`Value for ${slot.setting}`}
          description={secrets[slot.slot_id] ? 'Sent from Credential Manager; never shown or stored with the plan.' : 'Not chosen: the value written in the file is sent.'}
          data={logins} value={secrets[slot.slot_id] ?? null}
          onChange={(v) => { const next = { ...secrets }; if (v) next[slot.slot_id] = v; else delete next[slot.slot_id]; onSecrets(next); }} />
      ))}
    </Stack>
  );
}

function DeviceFiles({ role, device, choice, onChange }: { role: Role; device: Device; choice: Choice; onChange: (c: Choice) => void }) {
  const images = useFirmwareImages();
  const refs = useCredentialRefs(device.project_id);
  const logins = (refs.data ?? []).map((r) => ({ value: r.id, label: r.name }));
  const fitting = (images.data ?? []).filter((i) => i.status === 'approved'
    && (i.compatible_models.length === 0 || i.compatible_models.includes(device.model)));
  const set = (part: Partial<Choice>) => onChange({ ...choice, ...part });
  const { missing } = planSteps(role, choice, device);
  const hasFile = role.steps.includes('base') || role.steps.includes('file');
  return (
    <Card withBorder>
      <Group justify="space-between" mb={4} wrap="nowrap" align="flex-start">
        <Title order={3} size="h5">{role.title} · {device.name}</Title>
        {missing.length === 0
          ? <Badge color="teal" variant="light" leftSection={<IconCheck size={12} />} tt="none" style={{ flexShrink: 0 }}>Ready</Badge>
          : <Badge color="orange" variant="light" leftSection={<IconAlertTriangle size={12} />} tt="none" style={{ flexShrink: 0 }}>To choose</Badge>}
      </Group>
      {missing.length > 0 && <Text size="xs" c="orange" mb="xs">Still needed: {missing.join(', ')}.</Text>}
      <Stack gap="sm">
        {role.steps.includes('first_login') && device.capabilities.includes('supports_first_login_setup') && (
          <Checkbox checked={choice.firstLogin} onChange={(e) => set({ firstLogin: e.currentTarget.checked })}
            label="New unit (factory default): set its approved password at the first login"
            description="Leave this off for a unit that already has the approved password." />
        )}
        <Stack gap={4}>
          <Select label="Firmware" description={fitting.length ? 'An approved image for this model, or leave it as it is.' : 'No approved image for this model yet (Firmware page).'}
            placeholder="Keep the firmware it has" clearable w="100%" maw={420}
            data={fitting.map((i) => ({ value: i.id, label: `${i.version} · ${i.filename}` }))}
            value={choice.imageId} onChange={(v) => set({ imageId: v })} />
          {choice.imageId && (
            <Group gap="md">
              <Checkbox size="xs" label="Allowed to install an older approved version" checked={choice.allowDowngrade}
                onChange={(e) => set({ allowDowngrade: e.currentTarget.checked })} />
              {device.capabilities.includes('supports_firmware_secondary_image') && (
                <Checkbox size="xs" label="Also write it into the backup slot" checked={choice.alsoSecondary}
                  onChange={(e) => set({ alsoSecondary: e.currentTarget.checked })} />
              )}
            </Group>
          )}
        </Stack>
        {role.steps.includes('base') && (
          <FilePick device={device} label="Base file" description="The full backup restored first (complete file)." logins={logins}
            value={choice.baseId} onChange={(v) => set({ baseId: v })} />
        )}
        {role.steps.includes('site') && (
          <FilePick device={device} label="Site file" description="The script loaded after the base file (additions)." logins={logins}
            value={choice.siteId} onChange={(v) => set({ siteId: v })} secrets={choice.secrets} onSecrets={(s) => set({ secrets: s })} />
        )}
        {role.steps.includes('file') && (
          <FilePick device={device} label="Team file" description="The complete file this switch gets." logins={logins}
            value={choice.fileId} onChange={(v) => set({ fileId: v })} />
        )}
        {hasFile && (
          <Select label="Login after loading (optional)" clearable w="100%" maw={420} data={logins} value={choice.loginAfter}
            placeholder="Same login as now"
            description="If the file sets another password (FortiGate base file; team files set the approved one), choose that login."
            onChange={(v) => set({ loginAfter: v })} />
        )}
      </Stack>
    </Card>
  );
}

/** Step 2: files and firmware per device. */
export function FilesStep({ roles, choices, onChange }: {
  roles: { role: Role; device: Device }[];
  choices: Partial<Record<string, Choice>>;
  onChange: (key: string, c: Choice) => void;
}) {
  if (roles.length === 0) return <Alert color="gray">Add the devices first (step 1).</Alert>;
  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      {roles.map(({ role, device }) => (
        <DeviceFiles key={role.key} role={role} device={device} choice={choices[role.key] ?? EMPTY_CHOICE}
          onChange={(c) => onChange(role.key, c)} />
      ))}
    </SimpleGrid>
  );
}

import { Badge, Button, Card, Checkbox, FileButton, Group, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconUpload } from '@tabler/icons-react';
import { useEffect } from 'react';

import { useAction, useConfig, useConfigs, useCredentialRefs, useFirmwareImages, useLoginDefaults } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { Device, Project } from '../../types/api';
import { keptPreviousLogin, type Choice, type Choices, EMPTY_CHOICE, planSteps } from './choices';
import { GeneratePanel } from './GeneratePanel';
import { roleDefaults, type Role } from './roles';
import { EmptyState } from '../../components/EmptyState';

/** Choose one of the device's imported files, or import one; shows what UNDM found in it. */
function FilePick({ device, label, description, value, onChange, secrets, onSecrets, logins, defaultSecret }: {
  device: Device; label: string; description: string; value: string | null; onChange: (id: string | null) => void;
  secrets?: Record<string, string>; onSecrets?: (s: Record<string, string>, filled: boolean) => void; logins: { value: string; label: string }[];
  /** Login filled into the file's secret settings once (the tunnel key for all systems). */
  defaultSecret?: string | null;
}) {
  const configs = useConfigs(device.id);
  const chosen = useConfig(value);
  const imp = useAction(async (f: File) => api.importConfig(device.id, f.name, await f.text()), 'File imported and checked');
  const files = (configs.data ?? []).filter((v) => v.kind === 'imported');
  const report = chosen.data?.inspection;
  const slots = report?.secret_slots ?? [];
  useEffect(() => {
    if (!defaultSecret || !secrets || !onSecrets || slots.length === 0) return;
    const empty = slots.filter((slot) => !secrets[slot.slot_id]);
    if (empty.length === 0) return;
    const next = { ...secrets };
    for (const slot of empty) next[slot.slot_id] = defaultSecret;
    onSecrets(next, true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultSecret, slots.map((x) => x.slot_id).join(',')]);
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
          onChange={(v) => { const next = { ...secrets }; if (v) next[slot.slot_id] = v; else delete next[slot.slot_id]; onSecrets(next, false); }} />
      ))}
    </Stack>
  );
}

/** FortiGate license (optional, D-109): loaded as the plan's last step when the file is here;
 *  otherwise later from the device's menu (⋯ → Load license…). */
function LicensePick({ device, choice, onChange }: {
  device: Device; choice: Choice; onChange: (id: string | null, name?: string) => void;
}) {
  const upload = useAction((f: File) => api.uploadLicense(device.id, f), 'License file kept for this FortiGate', { errorInDialog: true });
  return (
    <Stack gap={4}>
      <Text size="sm" fw={500}>License file (optional)</Text>
      {choice.licenseId ? (
        <Group gap="xs">
          <Badge color="teal" variant="light" tt="none">{choice.licenseName || 'license file'}</Badge>
          <Text size="xs" c="dimmed">loaded as the last step of the plan</Text>
          <Button size="compact-xs" variant="subtle" color="red" onClick={() => onChange(null)}>Remove</Button>
        </Group>
      ) : (
        <Group gap="xs" align="center">
          <FileButton onChange={(f) => { if (f) upload.mutate(f, { onSuccess: (v) => onChange(v.id, v.filename) }); }}>
            {(props) => <Button {...props} size="xs" variant="light" leftSection={<IconUpload size={14} />} loading={upload.isPending}>Choose the license file…</Button>}
          </FileButton>
          <Text size="xs" c="dimmed">Not here yet? Leave it: load it later from the FortiGate's menu (⋯ → Load license…).</Text>
        </Group>
      )}
      {upload.error && <Text size="xs" c="red">{upload.error.message}</Text>}
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
  const needsLoginAfter = (!!role.loginAfter && device.environment !== 'simulated') || keptPreviousLogin(device);
  // Both image slots hold the approved version (team practice; 2930F and Black Box, D-110).
  const bothBanks = device.capabilities.includes('supports_firmware_secondary_image');
  // Defaults for all systems (D-105), each filled once for a real device; a cleared choice stays cleared.
  const defaults = useLoginDefaults();
  const real = device.environment !== 'simulated';
  const preset = roleDefaults(role, defaults.data);
  const filled = choice.filled ?? [];
  useEffect(() => {
    if (real && hasFile && preset.loginAfter && !choice.loginAfter && !filled.includes('loginAfter')) {
      onChange({ ...choice, loginAfter: preset.loginAfter, filled: [...filled, 'loginAfter'] });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset.loginAfter]);
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
        {role.steps.includes('firmware') && <Stack gap={4}>
          <Select label={role.guided ? 'Software package' : 'Firmware'}
            description={role.guided
              ? (fitting.length ? 'The approved package UNDM hands out for its portal (with its SHA-256).' : 'No approved package for this model yet: upload it on the Firmware page with its SHA-256 and approve it.')
              : (fitting.length ? 'An approved image for this model, or leave it as it is.' : 'No approved image for this model yet (Firmware page).')}
            placeholder={role.guided ? 'Choose the package' : 'Keep the firmware it has'} clearable w="100%" maw={420}
            data={fitting.map((i) => ({ value: i.id, label: `${i.version} · ${i.filename}` }))}
            value={choice.imageId} onChange={(v) => set({ imageId: v, alsoSecondary: !!v && bothBanks })} />
          {choice.imageId && !role.guided && (
            <Group gap="md">
              <Checkbox size="xs" label="Allowed to install an older approved version" checked={choice.allowDowngrade}
                onChange={(e) => set({ allowDowngrade: e.currentTarget.checked })} />
              {bothBanks && (
                <Checkbox size="xs" label="Also write it into the backup slot (both images the same)" checked={choice.alsoSecondary}
                  description={role.key === 'blackbox' ? 'A second upgrade fills the alternate image (a few minutes more, one more restart).' : undefined}
                  onChange={(e) => set({ alsoSecondary: e.currentTarget.checked })} />
              )}
            </Group>
          )}
        </Stack>}
        {role.steps.includes('base') && (
          <FilePick device={device} label="Base file" description="The full backup restored first (complete file)." logins={logins}
            value={choice.baseId} onChange={(v) => set({ baseId: v })} />
        )}
        {role.steps.includes('site') && (
          <FilePick device={device} label="Site file" description="The script loaded after the base file (additions)." logins={logins}
            value={choice.siteId} onChange={(v) => set({ siteId: v })} secrets={choice.secrets}
            defaultSecret={real && !filled.includes('secrets') ? preset.tunnelKey : null}
            onSecrets={(s, byDefault) => set({ secrets: s, ...(byDefault ? { filled: [...filled, 'secrets'] } : {}) })} />
        )}
        {role.steps.includes('file') && (
          <FilePick device={device} label={role.fileWords ? 'Configuration file' : 'Team file'}
            description={role.fileWords ?? 'The complete file this switch gets.'} logins={logins}
            value={choice.fileId} onChange={(v) => set({ fileId: v })} />
        )}
        {device.capabilities.includes('supports_license_file') && (
          <LicensePick device={device} choice={choice} onChange={(id, name) => set({ licenseId: id, licenseName: name })} />
        )}
        {hasFile && !role.fileKeepsLogin && (needsLoginAfter ? (
          <Select label="Login after loading" clearable w="100%" maw={420} data={logins} value={choice.loginAfter}
            placeholder="Choose the login" description={`Needed: ${role.loginAfter ?? 'the switch kept its previous password; its file sets the approved one: choose the approved login'}.`}
            error={choice.loginAfter ? undefined : 'Not chosen yet'}
            onChange={(v) => set({ loginAfter: v })} />
        ) : (
          <Select label="Login after loading (optional)" clearable w="100%" maw={420} data={logins} value={choice.loginAfter}
            placeholder="Same login as now"
            description="Leave empty when the device already uses the login its file sets (2930F after their console setup); otherwise choose that login."
            onChange={(v) => set({ loginAfter: v })} />
        ))}
      </Stack>
    </Card>
  );
}

/** Step 2: files and firmware per device. */
export function FilesStep({ project, roles, choices, onChange, onReplace }: {
  project?: Project;
  roles: { role: Role; device: Device }[];
  choices: Partial<Record<string, Choice>>;
  onChange: (key: string, c: Choice) => void;
  onReplace?: (next: Choices) => void;
}) {
  if (roles.length === 0) return <EmptyState>Add the devices first (step 1: System and devices).</EmptyState>;
  return (
    <Stack>
      {project && onReplace && <GeneratePanel project={project} roles={roles} choices={choices} onReplace={onReplace} />}
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        {roles.map(({ role, device }) => (
          <DeviceFiles key={role.key} role={role} device={device} choice={choices[role.key] ?? EMPTY_CHOICE}
            onChange={(c) => onChange(role.key, c)} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}

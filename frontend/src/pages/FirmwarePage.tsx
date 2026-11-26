import {
  Badge, Box, Button, Card, Checkbox, FileInput, Group, Modal, Select, SimpleGrid, Stack, Switch, Table, Tabs, TagsInput,
  Text, Textarea, TextInput, Tooltip,
} from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconShieldCheck, IconUpload, IconX } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { Hint } from '../components/Hint';
import { Notice } from '../components/Notice';
import { PageHeader, QueryState } from '../components/Page';
import { SafetyHint } from '../components/SafetyHint';
import { DialogError } from '../components/ConfirmDialog';
import { useConfirm } from '../hooks/useConfirm';
import { useAction, useDeviceModels, useFirmwareImages, useProjectDevices, useProjects } from '../hooks/queries';
import { api } from '../services/api';
import type { Compatibility, FirmwareImage } from '../types/api';
import { driverLabel, platformLabel, stateLabel } from '../services/labels';
import { paths } from '../paths';

const PLATFORMS = [
  { value: 'aos_switch', label: 'ArubaOS-Switch (e.g. 2930F)' }, { value: 'aoscx', label: 'Aruba AOS-CX' },
  { value: 'fortios', label: 'Fortinet FortiOS' }, { value: 'blackbox_lig1014a', label: 'Black Box LIG1014A' }, { value: 'iosxe', label: 'Cisco IOS-XE' },
  { value: 'flexi_sbts', label: 'Nokia Flexi BBU (SBTS package, loaded by hand)' },
];
const VENDOR_OF: Record<string, string> = { aos_switch: 'Aruba', aoscx: 'Aruba', fortios: 'Fortinet', iosxe: 'Cisco', blackbox_lig1014a: 'Black Box', flexi_sbts: 'Nokia' };
const OS_OF: Record<string, string> = { aos_switch: 'ArubaOS-Switch', aoscx: 'AOS-CX', fortios: 'FortiOS', iosxe: 'IOS-XE', blackbox_lig1014a: 'Black Box managed switch', flexi_sbts: 'SBTS (Flexi Multiradio 10)' };
const fmtSize = (b: number) => (b > 1024 ** 2 ? `${(b / 1024 ** 2).toFixed(1)} MiB` : `${(b / 1024).toFixed(1)} KiB`);

function UploadForm() {
  const models = useDeviceModels();
  const [file, setFile] = useState<File | null>(null);
  const [platform, setPlatform] = useState<string | null>('aos_switch');
  const [version, setVersion] = useState('');
  const [compatible, setCompatible] = useState<string[]>([]);
  const [sha, setSha] = useState('');
  const [minFrom, setMinFrom] = useState('');
  const [notes, setNotes] = useState('');
  const upload = useAction(() => {
    const form = new FormData();
    form.append('file', file!);
    form.append('vendor', VENDOR_OF[platform ?? ''] ?? '');
    form.append('platform', platform ?? '');
    form.append('version', version);
    form.append('compatible_models', compatible.join(','));
    if (sha.trim()) form.append('vendor_sha256', sha.trim());
    if (minFrom.trim()) form.append('min_from_version', minFrom.trim());
    form.append('release_notes', notes);
    return api.uploadFirmware(form);
  }, (img) => `Uploaded ${img.filename}${img.integrity_verified ? ' (checksum verified)' : ''}`);
  const missing = [!file && 'the image file', !version.trim() && 'the version',
    compatible.length === 0 && 'at least one compatible model (type it, then press Enter)'].filter(Boolean);
  const suggestions = (models.data ?? []).filter((m) => m.os_family === OS_OF[platform ?? '']).map((m) => m.model);

  return (
    <Card withBorder>
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <FileInput label="Firmware image file" placeholder="Choose the vendor image" value={file} onChange={setFile} required />
          <Select label="Platform" data={PLATFORMS} value={platform} onChange={setPlatform} allowDeselect={false} />
          <TextInput label="Version" placeholder="as reported by the device, e.g. WC.16.11.0003" value={version} onChange={(e) => setVersion(e.currentTarget.value)} required />
          <TagsInput label="Compatible models" placeholder="choose from the list, or type and press Enter" data={suggestions} value={compatible} onChange={setCompatible} />
          <TextInput label="Vendor checksum (SHA-256 or SHA-512)" description="Copy it from the vendor's download page (Fortinet: the SHA-512 under 'Checksum'). MD5 is not accepted. Required for approval; it can also be added after the upload." value={sha} onChange={(e) => setSha(e.currentTarget.value)} />
          <TextInput label="Minimum version to upgrade from (optional)" description="Upgrade-path rule from the release notes" value={minFrom} onChange={(e) => setMinFrom(e.currentTarget.value)} />
        </SimpleGrid>
        <Textarea label="Release notes / reference" autosize minRows={2} value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
        <Group>
          <Button leftSection={<IconUpload size={16} />} loading={upload.isPending} disabled={!file || !version.trim() || compatible.length === 0}
            onClick={() => upload.mutate(undefined, { onSuccess: () => { setFile(null); setVersion(''); setSha(''); setMinFrom(''); setNotes(''); } })}>
            Upload to repository
          </Button>
          <Text size="xs" c="dimmed">{missing.length ? `Still needed: ${missing.join(', ')}.`
            : "Only upload images obtained from the vendor. The file is stored in the backend's data folder."}</Text>
        </Group>
      </Stack>
    </Card>
  );
}

function ImageTable({ images }: { images: FirmwareImage[] }) {
  const approve = useAction((id: string) => api.approveFirmware(id), 'Image approved');
  const [overriding, setOverriding] = useState<FirmwareImage | null>(null);
  const [reason, setReason] = useState('');
  const reasonText = reason.trim().replace(/\s+/g, ' ');
  const approveUnverified = useAction(() => api.approveFirmware(overriding!.id, reasonText),
    'Image approved without the vendor checksum; the reason is recorded', { errorInDialog: true });
  const retire = useAction((id: string) => api.retireFirmware(id), 'Image retired', { errorInDialog: true });
  const del = useAction((id: string) => api.deleteFirmware(id), 'Image deleted', { errorInDialog: true });
  const [ask, confirmDialog] = useConfirm();
  const [checking, setChecking] = useState<FirmwareImage | null>(null);
  const [checksum, setChecksum] = useState('');
  const verify = useAction(() => api.addFirmwareChecksum(checking!.id, checksum.trim()), 'Checksum matched: image verified', { errorInDialog: true });
  return (
    <>
    <Modal opened={checking !== null} onClose={() => setChecking(null)} title={`Vendor checksum for ${checking?.filename ?? ''}`}>
      <Stack>
        <Text size="sm">Paste the SHA-256 or SHA-512 the vendor publishes for this file (Fortinet: the SHA-512 under
          'Checksum' next to the download). UNDM computes the same checksum of the stored file and compares; MD5 is not accepted.</Text>
        <TextInput label="Vendor checksum" value={checksum} onChange={(e) => setChecksum(e.currentTarget.value)} ff="monospace" />
        <DialogError error={verify.error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setChecking(null)}>Cancel</Button>
          <Button disabled={!checksum.trim()} loading={verify.isPending}
            onClick={() => verify.mutate(undefined, { onSuccess: () => { setChecking(null); setChecksum(''); } })}>Verify</Button>
        </Group>
      </Stack>
    </Modal>
    <Modal opened={overriding !== null} onClose={() => setOverriding(null)} title={`Approve ${overriding?.filename ?? ''} without a vendor checksum`}>
      <Stack>
        <Notice kind="caution" details="The reason and your name are recorded in the audit log, shown with the image, and repeated as a warning in every firmware plan that uses it.">
          UNDM cannot show that this file is the vendor's genuine, undamaged image. Approve it only if you obtained it from a
          source you trust.
        </Notice>
        <Text size="sm">If you can still get the vendor's SHA-256 or SHA-512, use "Add vendor checksum…" instead.</Text>
        <Textarea label="Reason for approving without the checksum" description="At least 10 characters, e.g. where the file came from."
          placeholder="e.g. taken from our approved software store" autosize minRows={2} maxLength={500}
          value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
        <DialogError error={approveUnverified.error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setOverriding(null)}>Cancel</Button>
          <Button color="orange" disabled={reasonText.length < 10} loading={approveUnverified.isPending}
            onClick={() => approveUnverified.mutate(undefined, { onSuccess: () => { setOverriding(null); setReason(''); } })}>
            Approve without checksum
          </Button>
        </Group>
      </Stack>
    </Modal>
    {confirmDialog}
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={900}>
        <Table verticalSpacing="xs" horizontalSpacing="md">
          <Table.Thead><Table.Tr><Table.Th>Version</Table.Th><Table.Th>For</Table.Th><Table.Th>File</Table.Th><Table.Th>Models</Table.Th>
            <Table.Th>Checksum</Table.Th><Table.Th>Status</Table.Th><Table.Th>Actions</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {images.map((i) => (
              <Table.Tr key={i.id}>
                <Table.Td><Text fw={600} size="sm">{i.version}</Text>{i.min_from_version && <Text size="xs" c="dimmed">from ≥ {i.min_from_version}</Text>}</Table.Td>
                <Table.Td>{platformLabel(i.platform)}</Table.Td>
                <Table.Td><Text size="sm">{i.filename}</Text><Text size="xs" c="dimmed">{fmtSize(i.size_bytes)}</Text></Table.Td>
                <Table.Td><Text size="sm">{i.compatible_models.join(', ')}</Text></Table.Td>
                <Table.Td>{i.integrity_verified
                  ? <Tooltip label={`${i.vendor_sha512 ? 'SHA-512' : 'SHA-256'} matched the vendor-published checksum`}><Badge color="teal" variant="light" leftSection={<IconShieldCheck size={12} />}>Verified</Badge></Tooltip>
                  : <Group gap={4} wrap="nowrap">
                      {i.status === 'approved' && i.unverified_reason
                        ? <Tooltip multiline w={320} label={`Approved by ${i.approved_by ?? '?'} without the vendor's checksum. Reason: ${i.unverified_reason}`}>
                            <Badge color="orange" variant="light" leftSection={<IconAlertTriangle size={12} />}>Not verified · approved with reason</Badge></Tooltip>
                        : <Tooltip label="No vendor checksum was supplied. Add it, or approve the image with a written reason."><Badge color="yellow" variant="light" leftSection={<IconAlertTriangle size={12} />}>Not verified</Badge></Tooltip>}
                      {i.status !== 'retired' && <Button size="compact-xs" variant="light" onClick={() => { setChecksum(''); setChecking(i); }}>Add vendor checksum…</Button>}
                    </Group>}</Table.Td>
                <Table.Td><Badge color={i.status === 'approved' ? 'teal' : i.status === 'retired' ? 'gray' : 'blue'} variant="light">{stateLabel(i.status)}</Badge>
                  {i.approved_by && <Text size="xs" c="dimmed">by {i.approved_by}</Text>}</Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    {i.status === 'uploaded' && (i.integrity_verified
                      ? <Button size="compact-xs" onClick={() => approve.mutate(i.id)}>Approve</Button>
                      : <Button size="compact-xs" color="orange" variant="light" onClick={() => { setReason(''); setOverriding(i); }}>Approve without checksum…</Button>)}
                    {i.status === 'approved' && <Button size="compact-xs" variant="default" onClick={() => ask({
                      title: `Retire ${i.filename}?`, confirmLabel: 'Retire image', color: 'orange',
                      message: 'New upgrade plans can no longer use it. Plans already made keep their record. The file stays until you delete it.',
                      onConfirm: () => retire.mutateAsync(i.id) })}>Retire</Button>}
                    <Button size="compact-xs" variant="subtle" color="red" onClick={() => ask({
                      title: `Delete ${i.filename}?`, confirmLabel: 'Delete image',
                      message: 'The file is removed from this PC. Upload it again if you need it later.',
                      onConfirm: () => del.mutateAsync(i.id) })}>Delete</Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {images.length === 0 && <Table.Tr><Table.Td colSpan={7}><Text c="dimmed" ta="center" p="md">No firmware images yet. Upload one above.</Text></Table.Td></Table.Tr>}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
    </>
  );
}

function Planner({ images }: { images: FirmwareImage[] }) {
  const projects = useProjects();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [dryRun, setDryRun] = useState(false);
  const [allowDowngrade, setAllowDowngrade] = useState(false);
  const [alsoSecondary, setAlsoSecondary] = useState(false);
  const [results, setResults] = useState<Compatibility[] | null>(null);
  const devices = useProjectDevices(projectId ?? '');
  const navigate = useNavigate();
  const check = useAction(() => api.firmwareCompatibility(imageId!, sel));
  const create = useAction(() => api.createFirmwareDeployment(projectId!, { device_ids: sel, image_id: imageId!, dry_run: dryRun, allow_downgrade: allowDowngrade, also_secondary: alsoSecondary }),
    (d) => `Upgrade plan created: ${stateLabel(d.state).toLowerCase()}`);
  const approved = images.filter((i) => i.status === 'approved');
  const chosen = approved.find((i) => i.id === imageId);
  const allOk = !!results && results.length === sel.length && results.every((r) => r.compatible);

  return (
    <Stack>
      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Approved image" placeholder={approved.length ? 'Choose an image' : 'Approve an image first'}
            data={approved.map((i) => ({ value: i.id, label: `${platformLabel(i.platform)} ${i.version} (${i.filename})${i.integrity_verified ? '' : ' · NOT VERIFIED'}` }))}
            value={imageId} onChange={(v) => { setImageId(v); setResults(null); }} />
          <Select label="System" data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
            value={projectId} onChange={(v) => { setProjectId(v); setSel([]); setResults(null); }} />
        </SimpleGrid>
        {chosen && !chosen.integrity_verified && (
          <Notice mt="md" kind="caution" title="This image is not verified against the vendor's checksum">
            Approved by {chosen.approved_by ?? '?'} with the reason: “{chosen.unverified_reason ?? ''}”. The plan records this as a warning.
          </Notice>
        )}
      </Card>
      {projectId && (
        <Card withBorder>
          <Table.ScrollContainer minWidth={520}>
            <Table verticalSpacing={4}>
              <Table.Thead><Table.Tr><Table.Th w={36} /><Table.Th>Device</Table.Th><Table.Th>Model</Table.Th><Table.Th>Connects by</Table.Th><Table.Th>Firmware now (last read)</Table.Th><Table.Th>Compatibility</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(devices.data ?? []).map((d) => {
                  const r = results?.find((x) => x.device_id === d.id);
                  return (
                    <Table.Tr key={d.id}>
                      <Table.Td><Checkbox aria-label={`Upgrade ${d.name}`} checked={sel.includes(d.id)}
                        onChange={() => { setResults(null); setSel((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id])); }} /></Table.Td>
                      <Table.Td>{d.name}</Table.Td><Table.Td>{d.model}</Table.Td><Table.Td><Text size="xs">{driverLabel(d.driver_id)}</Text></Table.Td>
                      <Table.Td>{String(d.observed_facts?.os_version ?? '— (use Retrieve information on the device page)')}</Table.Td>
                      <Table.Td>{r && (r.compatible ? <Stack gap={2}><Badge color="teal" variant="light" leftSection={<IconCheck size={12} />}>Compatible</Badge>
                          {r.issues.map((i) => <Text key={i.code} size="xs" c="orange">{i.message}</Text>)}</Stack>
                        : <Stack gap={2}><Badge color="red" variant="light" leftSection={<IconX size={12} />}>Not compatible</Badge>
                          {r.issues.map((i) => <Text key={i.code} size="xs" c="red">{i.message}</Text>)}</Stack>)}</Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group mt="md">
            <Button variant="default" disabled={!imageId || sel.length === 0} loading={check.isPending}
              onClick={() => check.mutate(undefined, { onSuccess: setResults })}>Check compatibility (offline)</Button>
            <Switch label="Dry run (read versions only, no approval)" checked={dryRun} onChange={(e) => setDryRun(e.currentTarget.checked)} />
            <Checkbox label="Install the approved version even on devices that run a newer one (downgrade)"
              description="For a system that requires an older approved release, e.g. new units shipping with a newer one."
              checked={allowDowngrade} onChange={(e) => setAllowDowngrade(e.currentTarget.checked)} />
            <Checkbox label="Also write the approved version into the secondary flash"
              description="After the device runs it from primary (it keeps booting from primary). Devices already on the version get only their secondary written."
              checked={alsoSecondary} onChange={(e) => setAlsoSecondary(e.currentTarget.checked)} />
            <Button disabled={!allOk} loading={create.isPending}
              onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(paths.plan(d.id)) })}>Create upgrade plan</Button>
          </Group>
          {!dryRun && <Box mt="xs"><SafetyHint firmware real={(devices.data ?? []).some((d) => sel.includes(d.id) && d.environment !== 'simulated')} /></Box>}
          {!allOk && <Text size="xs" c="dimmed" mt="xs">{!imageId ? 'Choose an approved image.' : sel.length === 0 ? 'Tick the devices to upgrade.'
            : !results || results.length !== sel.length ? 'Check compatibility first: the plan is made only for devices the image fits.'
              : 'An image that does not fit every ticked device cannot be planned: untick those devices.'}</Text>}
        </Card>
      )}
    </Stack>
  );
}

export function FirmwarePage() {
  const images = useFirmwareImages();
  return (
    <>
      <PageHeader title="Firmware" description="Upload firmware images, approve them, then make an upgrade plan for the devices that need them." />
      <Hint mb="md" more={<>Real devices with an upgrade procedure: Aruba 2930F, FortiGate 101F and Black Box LIG1014A. Each has
        been run on bench units and stays marked experimental. The device fetches the image from this PC and restarts into
        it, so use a spare unit on an isolated bench. Other real models are shown as not compatible. A dry run only reads the
        running version.</>}>
        Simulated devices can always be upgraded; real devices need Firmware changes on (Settings → Safety).
      </Hint>
      <QueryState isLoading={images.isLoading} error={images.error} />
      <Tabs defaultValue="repo" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="repo">Images ({images.data?.length ?? 0})</Tabs.Tab>
          <Tabs.Tab value="plan">Make an upgrade plan</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="repo"><Stack><UploadForm /><ImageTable images={images.data ?? []} /></Stack></Tabs.Panel>
        <Tabs.Panel value="plan"><Planner images={images.data ?? []} /></Tabs.Panel>
      </Tabs>
      <Text size="xs" c="dimmed" mt="md">Upgrade plans and their history are on the Plans page.</Text>
    </>
  );
}

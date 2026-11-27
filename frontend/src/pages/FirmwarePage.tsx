import { ActionIcon, Box, Button, Card, Checkbox, FileInput, Group, Menu, Modal, Select, SimpleGrid, Stack, Switch, Table, Tabs, TagsInput,
  Text, Textarea, TextInput, Tooltip,
} from '@mantine/core';
import { InlineStatus } from '../components/InlineStatus';
import { Tag } from '../components/Badges';
import { IconAlertTriangle, IconCheck, IconDots, IconShieldCheck, IconUpload, IconX } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { ActionsHeader } from '../components/DataTable';
import { Hint } from '../components/Hint';
import { Notice } from '../components/Notice';
import { PageHeader, QueryState } from '../components/Page';
import { SafetyHint } from '../components/SafetyHint';
import { DialogError } from '../components/ConfirmDialog';
import { useConfirm } from '../hooks/useConfirm';
import { useAction, useDeviceModels, useDrivers, useFirmwareImages, useProjectDevices, useProjects } from '../hooks/queries';
import { api } from '../services/api';
import type { Compatibility, DeviceModel, Driver, FirmwareImage } from '../types/api';
import { ReasonButton } from '../components/ReasonButton';
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

/** The platform of a catalog model: the one its real driver uses (D-122). */
function platformOfModel(model: DeviceModel | undefined, drivers: Driver[] | undefined): string | null {
  if (!model || !drivers) return null;
  const platforms = model.drivers.map((id) => drivers.find((d) => d.driver_id === id)).filter((d) => d && !d.simulated).map((d) => d!.platform);
  const known = platforms.filter((p) => PLATFORMS.some((x) => x.value === p));
  return known[0] ?? null;
}

/** Upload an image for a device model (D-122): the platform and the first compatible model
 *  follow from the model; the platform can still be chosen for a model UNDM cannot place. */
function UploadForm({ initialModel, onDone }: { initialModel: string | null; onDone: () => void }) {
  const models = useDeviceModels();
  const drivers = useDrivers();
  const real = (models.data ?? []).filter((m) => platformOfModel(m, drivers.data));
  const [modelId, setModelId] = useState<string | null>(null);
  const chosen = (models.data ?? []).find((m) => m.model_id === modelId)
    ?? (modelId === null && initialModel ? (models.data ?? []).find((m) => m.model === initialModel) : undefined);
  const derived = platformOfModel(chosen, drivers.data);
  const [platformChoice, setPlatform] = useState<string | null>(null);
  const platform = derived ?? platformChoice;
  const [file, setFile] = useState<File | null>(null);
  const [version, setVersion] = useState('');
  const [extra, setCompatible] = useState<string[] | null>(null);
  const compatible = extra ?? (chosen ? [chosen.model] : []);
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
  }, (img) => `Uploaded ${img.filename}${img.integrity_verified ? ' (checksum verified)' : ''}`, { errorInDialog: true });
  const missing = [!platform && 'the device model', !file && 'the image file', !version.trim() && 'the version',
    compatible.length === 0 && 'at least one compatible model (type it, then press Enter)'].filter(Boolean);
  const suggestions = (models.data ?? []).filter((m) => m.os_family === OS_OF[platform ?? '']).map((m) => m.model);

  return (
      <Stack>
        <Select label="Device model" placeholder="The model this image is for" searchable data-autofocus
          data={real.map((m) => ({ value: m.model_id, label: `${m.manufacturer} ${m.model}` }))}
          value={chosen?.model_id ?? null} onChange={(v) => { setModelId(v); setCompatible(null); }}
          description={chosen && derived ? `Platform: ${PLATFORMS.find((x) => x.value === derived)?.label ?? derived}` : undefined} />
        {!(chosen && derived) && (
          <Select label="Platform" placeholder="Choose the platform" data={PLATFORMS} value={platformChoice} onChange={setPlatform} />
        )}
        <FileInput label="Image file" placeholder="Choose the vendor's file" value={file} onChange={setFile} required />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Version" placeholder="e.g. WC.16.11.0003" description="As the device reports it." value={version}
            onChange={(e) => setVersion(e.currentTarget.value)} required />
          <TagsInput label="Compatible models" placeholder="Choose, or type and press Enter" data={suggestions} value={compatible}
            onChange={setCompatible} description="The models it may be loaded on." />
          <TextInput label="Vendor checksum" placeholder="SHA-256 or SHA-512" value={sha} onChange={(e) => setSha(e.currentTarget.value)}
            description="Only one the vendor publishes. None? Leave it empty and approve with a reason." />
          <TextInput label="Oldest version it upgrades from" placeholder="Optional" value={minFrom}
            onChange={(e) => setMinFrom(e.currentTarget.value)} description="From the release notes, if they say." />
        </SimpleGrid>
        <Textarea label="Release notes or reference" placeholder="Optional" autosize minRows={2} value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
        <Hint more={<>Fortinet publishes the SHA-512 under “Checksum” next to the download; MD5 is not accepted. Without it the
          image can be uploaded, and the checksum added later (“Add vendor checksum…”). Only upload images obtained from the
          vendor: the file is kept in UNDM's data folder.</>}>The checksum proves the file is the vendor's, undamaged.</Hint>
        <DialogError error={upload.error} />
        <Group justify="flex-end" align="flex-start">
          <Button variant="default" onClick={onDone}>Cancel</Button>
          <ReasonButton leftSection={<IconUpload size={16} />} loading={upload.isPending} disabled={missing.length > 0}
            reason={missing.length ? `Still needed: ${missing.join(', ')}.` : null}
            onClick={() => upload.mutate(undefined, { onSuccess: onDone })}>
            Upload
          </ReasonButton>
        </Group>
      </Stack>
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
      <Table.ScrollContainer minWidth={760}>
        <Table aria-label="Firmware images" verticalSpacing="sm" horizontalSpacing="md">
          <Table.Thead><Table.Tr><Table.Th>Image</Table.Th><Table.Th>For</Table.Th><Table.Th>Status</Table.Th>
            <Table.Th>Checksum</Table.Th><ActionsHeader /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {images.map((i) => (
              <Table.Tr key={i.id}>
                <Table.Td maw={340}>
                  <Text fw={600} size="sm" style={{ overflowWrap: 'anywhere' }}>{i.version}</Text>
                  <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{i.filename} · {fmtSize(i.size_bytes)}</Text>
                  {i.min_from_version && <Text size="xs" c="dimmed">Upgrades from {i.min_from_version} or later</Text>}
                </Table.Td>
                <Table.Td><Text size="sm">{platformLabel(i.platform)}</Text>
                  <Text size="xs" c="dimmed">{i.compatible_models.join(', ') || 'no models listed'}</Text></Table.Td>
                <Table.Td><Tag tone={i.status === 'approved' ? 'success' : i.status === 'retired' ? 'neutral' : 'info'}>{stateLabel(i.status)}</Tag>
                  {i.approved_by && <Text size="xs" c="dimmed" mt={2}>by {i.approved_by}</Text>}</Table.Td>
                <Table.Td>{i.integrity_verified
                  ? <Tooltip label={`${i.vendor_sha512 ? 'SHA-512' : 'SHA-256'} matched the vendor-published checksum`}><Tag tone="success" icon={<IconShieldCheck size={12} />}>Verified</Tag></Tooltip>
                  : i.status === 'approved' && i.unverified_reason
                    ? <Tooltip multiline w={320} label={`Approved by ${i.approved_by ?? '?'} without the vendor's checksum. Reason: ${i.unverified_reason}`}>
                        <Tag tone="warning" icon={<IconAlertTriangle size={12} />}>Approved with a reason</Tag></Tooltip>
                    : <Tooltip label="No vendor checksum was supplied. Add it, or approve the image with a written reason."><Tag tone="warning" icon={<IconAlertTriangle size={12} />}>Not verified</Tag></Tooltip>}</Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    {i.status === 'uploaded' && (i.integrity_verified
                      ? <Button size="compact-sm" onClick={() => approve.mutate(i.id)}>Approve</Button>
                      : <Button size="compact-sm" variant="light" onClick={() => { setReason(''); setOverriding(i); }}>Approve…</Button>)}
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target><ActionIcon variant="subtle" aria-label={`More for ${i.filename}`}><IconDots size={16} /></ActionIcon></Menu.Target>
                      <Menu.Dropdown>
                        {!i.integrity_verified && i.status !== 'retired' && <Menu.Item onClick={() => { setChecksum(''); setChecking(i); }}>Add vendor checksum…</Menu.Item>}
                        {i.status === 'approved' && <Menu.Item onClick={() => ask({
                          title: `Retire ${i.filename}?`, confirmLabel: 'Retire image', color: 'orange',
                          message: 'New upgrade plans can no longer use it. Plans already made keep their record. The file stays until you delete it.',
                          onConfirm: () => retire.mutateAsync(i.id) })}>Retire…</Menu.Item>}
                        <Menu.Item color="red" onClick={() => ask({
                          title: `Delete ${i.filename}?`, confirmLabel: 'Delete image',
                          message: 'The file is removed from this PC. Upload it again if you need it later.',
                          onConfirm: () => del.mutateAsync(i.id) })}>Delete…</Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {images.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" ta="center" p="md">No firmware images yet. Upload one above.</Text></Table.Td></Table.Tr>}
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
            <Table aria-label="Devices to upgrade" verticalSpacing={4}>
              <Table.Thead><Table.Tr><Table.Th w={36} /><Table.Th>Device</Table.Th><Table.Th>Model</Table.Th><Table.Th>Connects by</Table.Th><Table.Th>Firmware now (last read)</Table.Th><Table.Th>Compatibility</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(devices.data ?? []).map((d) => {
                  const r = results?.find((x) => x.device_id === d.id);
                  return (
                    <Table.Tr key={d.id}>
                      <Table.Td><Checkbox aria-label={`Upgrade ${d.name}`} checked={sel.includes(d.id)}
                        onChange={() => { setResults(null); setSel((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id])); }} /></Table.Td>
                      <Table.Td>{d.name}</Table.Td><Table.Td>{d.model}</Table.Td><Table.Td><Text size="xs">{driverLabel(d.driver_id)}</Text></Table.Td>
                      <Table.Td>{String(d.observed_facts?.os_version ?? '— (use Read information on the device page)')}</Table.Td>
                      <Table.Td>{r && (r.compatible ? <Stack gap={2}><Tag tone="success" icon={<IconCheck size={12} />}>Compatible</Tag>
                          {r.issues.map((i) => <InlineStatus key={i.code} tone="warning" size="xs">{i.message}</InlineStatus>)}</Stack>
                        : <Stack gap={2}><Tag tone="danger" icon={<IconX size={12} />}>Not compatible</Tag>
                          {r.issues.map((i) => <InlineStatus key={i.code} tone="danger" size="xs">{i.message}</InlineStatus>)}</Stack>)}</Table.Td>
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
            <Checkbox label="Also write the approved version into the backup slot"
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
  const [params, setParams] = useSearchParams();
  // `?model=` (from Stage a system: "no approved image for this model") opens the upload for it.
  const model = params.get('model');
  const [uploading, setUploading] = useState(!!model);
  const close = () => { setUploading(false); if (model) setParams({}, { replace: true }); };
  return (
    <>
      <PageHeader title="Firmware" description="Upload firmware images, approve them, then make an upgrade plan for the devices that need them."
        primary={<Button leftSection={<IconUpload size={16} />} onClick={() => setUploading(true)}>Upload image…</Button>} />
      <Modal opened={uploading} onClose={close} title="Upload a firmware image" size="lg">
        {uploading && <UploadForm initialModel={model} onDone={close} />}
      </Modal>
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
        <Tabs.Panel value="repo"><ImageTable images={images.data ?? []} /></Tabs.Panel>
        <Tabs.Panel value="plan"><Planner images={images.data ?? []} /></Tabs.Panel>
      </Tabs>
      <Text size="xs" c="dimmed" mt="md">Upgrade plans and their history are on the Plans page.</Text>
    </>
  );
}

import {
  Alert, Badge, Button, Card, Checkbox, FileInput, Group, Select, SimpleGrid, Stack, Switch, Table, Tabs, TagsInput,
  Text, Textarea, TextInput, Tooltip,
} from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconShieldCheck, IconUpload, IconX } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { PageHeader, QueryState } from '../components/Page';
import { useAction, useDeviceModels, useFirmwareImages, usePolicy, useProjectDevices, useProjects } from '../hooks/queries';
import { api } from '../services/api';
import type { Compatibility, FirmwareImage } from '../types/api';

const PLATFORMS = [
  { value: 'aos_switch', label: 'ArubaOS-Switch (e.g. 2930F)' }, { value: 'aoscx', label: 'Aruba AOS-CX' },
  { value: 'fortios', label: 'Fortinet FortiOS' }, { value: 'iosxe', label: 'Cisco IOS-XE' },
];
const VENDOR_OF: Record<string, string> = { aos_switch: 'Aruba', aoscx: 'Aruba', fortios: 'Fortinet', iosxe: 'Cisco' };
const OS_OF: Record<string, string> = { aos_switch: 'ArubaOS-Switch', aoscx: 'AOS-CX', fortios: 'FortiOS', iosxe: 'IOS-XE' };
const fmtSize = (b: number) => (b > 1024 ** 2 ? `${(b / 1024 ** 2).toFixed(1)} MiB` : `${(b / 1024).toFixed(1)} KiB`);

function UploadForm() {
  const models = useDeviceModels();
  const [file, setFile] = useState<File | null>(null);
  const [platform, setPlatform] = useState<string | null>('aoscx');
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
  const suggestions = (models.data ?? []).filter((m) => m.os_family === OS_OF[platform ?? '']).map((m) => m.model);

  return (
    <Card withBorder>
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <FileInput label="Firmware image file" placeholder="Choose the vendor image" value={file} onChange={setFile} required />
          <Select label="Platform" data={PLATFORMS} value={platform} onChange={setPlatform} allowDeselect={false} />
          <TextInput label="Version" placeholder="as reported by the device, e.g. WC.16.11.0003" value={version} onChange={(e) => setVersion(e.currentTarget.value)} required />
          <TagsInput label="Compatible models" placeholder="type and press Enter" data={suggestions} value={compatible} onChange={setCompatible} />
          <TextInput label="Vendor SHA-256" description="Copy from the vendor download page. Required for approval." value={sha} onChange={(e) => setSha(e.currentTarget.value)} />
          <TextInput label="Minimum version to upgrade from (optional)" description="Upgrade-path rule from the release notes" value={minFrom} onChange={(e) => setMinFrom(e.currentTarget.value)} />
        </SimpleGrid>
        <Textarea label="Release notes / reference" autosize minRows={2} value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
        <Group>
          <Button leftSection={<IconUpload size={16} />} loading={upload.isPending} disabled={!file || !version.trim() || compatible.length === 0}
            onClick={() => upload.mutate(undefined, { onSuccess: () => { setFile(null); setVersion(''); setSha(''); setMinFrom(''); setNotes(''); } })}>
            Upload to repository
          </Button>
          <Text size="xs" c="dimmed">Only upload images obtained from the vendor. The file is stored in the backend's data folder.</Text>
        </Group>
      </Stack>
    </Card>
  );
}

function ImageTable({ images }: { images: FirmwareImage[] }) {
  const approve = useAction((id: string) => api.approveFirmware(id), 'Image approved');
  const retire = useAction((id: string) => api.retireFirmware(id), 'Image retired');
  const del = useAction((id: string) => api.deleteFirmware(id), 'Image deleted');
  return (
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={900}>
        <Table verticalSpacing="xs" horizontalSpacing="md">
          <Table.Thead><Table.Tr><Table.Th>Version</Table.Th><Table.Th>Platform</Table.Th><Table.Th>File</Table.Th><Table.Th>Models</Table.Th>
            <Table.Th>Integrity</Table.Th><Table.Th>Status</Table.Th><Table.Th>Actions</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {images.map((i) => (
              <Table.Tr key={i.id}>
                <Table.Td><Text fw={600} size="sm">{i.version}</Text>{i.min_from_version && <Text size="xs" c="dimmed">from ≥ {i.min_from_version}</Text>}</Table.Td>
                <Table.Td>{i.platform}</Table.Td>
                <Table.Td><Text size="sm">{i.filename}</Text><Text size="xs" c="dimmed" ff="monospace">{fmtSize(i.size_bytes)} · {i.sha256.slice(0, 12)}…</Text></Table.Td>
                <Table.Td><Text size="sm">{i.compatible_models.join(', ')}</Text></Table.Td>
                <Table.Td>{i.integrity_verified
                  ? <Tooltip label="SHA-256 matched the vendor-published checksum"><Badge color="teal" variant="light" leftSection={<IconShieldCheck size={12} />}>verified</Badge></Tooltip>
                  : <Tooltip label="No vendor checksum was supplied, so the file cannot be approved"><Badge color="yellow" variant="light">not verified</Badge></Tooltip>}</Table.Td>
                <Table.Td><Badge color={i.status === 'approved' ? 'teal' : i.status === 'retired' ? 'gray' : 'blue'} variant="light">{i.status}</Badge>
                  {i.approved_by && <Text size="xs" c="dimmed">by {i.approved_by}</Text>}</Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    {i.status === 'uploaded' && <Button size="compact-xs" onClick={() => approve.mutate(i.id)} disabled={!i.integrity_verified}>Approve</Button>}
                    {i.status === 'approved' && <Button size="compact-xs" variant="default" onClick={() => retire.mutate(i.id)}>Retire</Button>}
                    <Button size="compact-xs" variant="subtle" color="red" onClick={() => { if (window.confirm(`Delete ${i.filename}?`)) del.mutate(i.id); }}>Delete</Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {images.length === 0 && <Table.Tr><Table.Td colSpan={7}><Text c="dimmed" ta="center" p="md">No images in the repository yet.</Text></Table.Td></Table.Tr>}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

function Planner({ images }: { images: FirmwareImage[] }) {
  const projects = useProjects();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [dryRun, setDryRun] = useState(false);
  const [allowDowngrade, setAllowDowngrade] = useState(false);
  const [results, setResults] = useState<Compatibility[] | null>(null);
  const devices = useProjectDevices(projectId ?? '');
  const navigate = useNavigate();
  const check = useAction(() => api.firmwareCompatibility(imageId!, sel));
  const create = useAction(() => api.createFirmwareDeployment(projectId!, { device_ids: sel, image_id: imageId!, dry_run: dryRun, allow_downgrade: allowDowngrade }),
    (d) => `Upgrade plan created: ${d.state.replaceAll('_', ' ')}`);
  const approved = images.filter((i) => i.status === 'approved');
  const allOk = !!results && results.length === sel.length && results.every((r) => r.compatible);

  return (
    <Stack>
      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Approved image" placeholder={approved.length ? 'Choose an image' : 'Approve an image first'}
            data={approved.map((i) => ({ value: i.id, label: `${i.platform} ${i.version} (${i.filename})` }))}
            value={imageId} onChange={(v) => { setImageId(v); setResults(null); }} />
          <Select label="Project" data={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
            value={projectId} onChange={(v) => { setProjectId(v); setSel([]); setResults(null); }} />
        </SimpleGrid>
      </Card>
      {projectId && (
        <Card withBorder>
          <Table verticalSpacing={4}>
            <Table.Thead><Table.Tr><Table.Th w={36} /><Table.Th>Device</Table.Th><Table.Th>Model</Table.Th><Table.Th>Driver</Table.Th><Table.Th>Running version (observed)</Table.Th><Table.Th>Compatibility</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {(devices.data ?? []).map((d) => {
                const r = results?.find((x) => x.device_id === d.id);
                return (
                  <Table.Tr key={d.id}>
                    <Table.Td><Checkbox aria-label={`Upgrade ${d.name}`} checked={sel.includes(d.id)}
                      onChange={() => { setResults(null); setSel((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id])); }} /></Table.Td>
                    <Table.Td>{d.name}</Table.Td><Table.Td>{d.model}</Table.Td><Table.Td><Text size="xs" ff="monospace">{d.driver_id}</Text></Table.Td>
                    <Table.Td>{String(d.observed_facts?.os_version ?? '— (retrieve information)')}</Table.Td>
                    <Table.Td>{r && (r.compatible ? <Badge color="teal" variant="light" leftSection={<IconCheck size={12} />}>compatible</Badge>
                      : <Stack gap={2}><Badge color="red" variant="light" leftSection={<IconX size={12} />}>not compatible</Badge>
                        {r.issues.map((i) => <Text key={i.code} size="xs" c="red">{i.message}</Text>)}</Stack>)}</Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
          <Group mt="md">
            <Button variant="default" disabled={!imageId || sel.length === 0} loading={check.isPending}
              onClick={() => check.mutate(undefined, { onSuccess: setResults })}>Check compatibility (offline)</Button>
            <Switch label="Dry run (read versions only, no approval)" checked={dryRun} onChange={(e) => setDryRun(e.currentTarget.checked)} />
            <Checkbox label="Install the approved version even on devices that run a newer one (downgrade)"
              description="For a project that requires an older approved release, e.g. new units shipping with a newer one."
              checked={allowDowngrade} onChange={(e) => setAllowDowngrade(e.currentTarget.checked)} />
            <Button disabled={!allOk} loading={create.isPending}
              onClick={() => create.mutate(undefined, { onSuccess: (d) => void navigate(`/deployments/${d.id}`) })}>Create upgrade plan</Button>
          </Group>
        </Card>
      )}
    </Stack>
  );
}

export function FirmwarePage() {
  const images = useFirmwareImages();
  const policy = usePolicy();
  const realFirmware = !!policy.data?.enable_real_device_writes && !!policy.data?.enable_real_device_firmware;
  return (
    <>
      <PageHeader title="Firmware Manager" description="Approved image repository, offline compatibility checks and controlled upgrade plans." />
      <Alert color="orange" icon={<IconAlertTriangle size={18} />} mb="md"
        title={realFirmware ? 'Firmware changes to real lab devices are ENABLED' : 'Real devices: dry runs only'}>
        Simulated devices can be upgraded freely. One real-device procedure exists and is <b>experimental, not yet run on
        hardware</b>: Aruba 2930F (ArubaOS-Switch), where the switch pulls the image from this PC over TFTP and restarts into it.
        Use it only on a spare unit on an isolated bench. {realFirmware
          ? 'Both safety switches are on for this server.'
          : 'Real upgrades stay blocked until both UNDM_ENABLE_REAL_DEVICE_WRITES and UNDM_ENABLE_REAL_DEVICE_FIRMWARE are set; dry runs (read the running version, change nothing) are allowed.'}{' '}
        Other real models are reported as incompatible until their procedure is implemented.
      </Alert>
      <QueryState isLoading={images.isLoading} error={images.error} />
      <Tabs defaultValue="repo" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="repo">Image repository ({images.data?.length ?? 0})</Tabs.Tab>
          <Tabs.Tab value="plan">Upgrade planning</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="repo"><Stack><UploadForm /><ImageTable images={images.data ?? []} /></Stack></Tabs.Panel>
        <Tabs.Panel value="plan"><Planner images={images.data ?? []} /></Tabs.Panel>
      </Tabs>
      <Text size="xs" c="dimmed" mt="md">Upgrade plans and their history appear in the Deployment Center.</Text>
    </>
  );
}

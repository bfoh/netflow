import { Button, Checkbox, FileInput, Group, List, Modal, Stack, Text, TextInput } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconFileImport } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { useAction } from '../../hooks/queries';
import { api, type SystemImport } from '../../services/api';
import { Notice } from '../../components/Notice';
import { paths } from '../../paths';

/** Export a system to one .undm file (D-087): no passwords, files as written. */
export function ExportSystemButton({ projectId }: { projectId: string }) {
  const [opened, { open, close }] = useDisclosure();
  return (
    <>
      <Button variant="default" leftSection={<IconDownload size={16} />} onClick={open}>Export…</Button>
      <ExportSystemDialog projectId={projectId} opened={opened} onClose={close} />
    </>
  );
}

export function ExportSystemDialog({ projectId, opened, onClose: close }: { projectId: string; opened: boolean; onClose: () => void }) {
  const [firmware, setFirmware] = useState(false);
  const run = useAction(() => api.exportSystem(projectId, firmware), (name) => `Saved ${name} to your downloads`, { errorInDialog: true });
  return (
    <>
      <Modal opened={opened} onClose={close} title="Export this system">
        <Stack>
          <Text size="sm">One <code>.undm</code> file with the system's settings, its devices, the names of its logins, its
            configuration files and its topology. A colleague imports it on their copy of UNDM.</Text>
          <Notice kind="caution" compact title="Keep the file confidential"
            details="Passwords are never exported: the logins arrive empty. But the team's configuration files are included as written.">
            The configuration files in it can hold passwords (for example Black Box files).
          </Notice>
          <Checkbox label="Include the approved firmware images for these devices (a much larger file)"
            checked={firmware} onChange={(e) => setFirmware(e.currentTarget.checked)} />
          <DialogError error={run.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close} data-autofocus>Cancel</Button>
            <Button leftSection={<IconDownload size={16} />} loading={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: close })}>Export</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

/** Every backup UNDM took of the system's devices, as text files in one zip (D-097). */
export function DownloadBackupsButton({ projectId, onDownloaded }: { projectId: string; onDownloaded?: () => void }) {
  const [opened, { open, close }] = useDisclosure();
  return (
    <>
      <Button variant="default" leftSection={<IconDownload size={16} />} onClick={open}>Backups…</Button>
      <DownloadBackupsDialog projectId={projectId} opened={opened} onClose={close} onDownloaded={onDownloaded} />
    </>
  );
}

export function DownloadBackupsDialog({ projectId, opened, onClose: close, onDownloaded }: {
  projectId: string; opened: boolean; onClose: () => void; onDownloaded?: () => void;
}) {
  const run = useAction(() => api.downloadBackups(projectId), (name) => `Saved ${name} to your downloads`, { errorInDialog: true });
  return (
    <>
      <Modal opened={opened} onClose={close} title="Download this system's backups">
        <Stack>
          <Text size="sm">One zip with a folder per device. Each file is the device's configuration as UNDM read it, just before a
            plan changed it or right after. A single backup can also be downloaded on its device's Files tab.</Text>
          <Notice kind="caution" compact title="Keep the file confidential">
            Device configurations can hold password hashes, community strings and site addressing.
          </Notice>
          <DialogError error={run.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close} data-autofocus>Cancel</Button>
            <Button leftSection={<IconDownload size={16} />} loading={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: () => { close(); onDownloaded?.(); } })}>Download</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

/** Import a .undm file as a new system; tells what to do next (store the passwords). */
export function ImportSystemButton() {
  const [opened, { open, close }] = useDisclosure();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [done, setDone] = useState<SystemImport | null>(null);
  const navigate = useNavigate();
  const run = useAction(() => api.importSystem(file!, name), (r) => `System ${r.project.name} imported`, { errorInDialog: true });
  const reset = () => { setFile(null); setName(''); setDone(null); run.reset(); close(); };
  return (
    <>
      <Button variant="default" leftSection={<IconFileImport size={16} />} onClick={open}>Import…</Button>
      <Modal opened={opened} onClose={reset} title="Import a system">
        {done ? (
          <Stack>
            <Text size="sm">Imported <b>{done.project.name}</b>: {done.summary.devices} devices, {done.summary.files} files
              {done.summary.firmware_added ? `, ${done.summary.firmware_added} firmware images (to approve on the Firmware page)` : ''}.</Text>
            {done.summary.logins.length > 0 && (
              <Notice kind="settled" compact title="Next: store the passwords">
                These logins came without passwords. Open the system, Logins tab, and set each one:
                <List size="xs" mt={4}>{done.summary.logins.map((l) => <List.Item key={l}>{l}</List.Item>)}</List>
              </Notice>
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={reset}>Close</Button>
              <Button onClick={() => { const id = done.project.id; reset(); void navigate(paths.system(id)); }}>Open the system</Button>
            </Group>
          </Stack>
        ) : (
          <Stack>
            <FileInput label="System file" placeholder="Choose a .undm file" accept=".undm,application/zip" value={file} onChange={setFile} />
            <TextInput label="Name (optional)" description="Leave empty to keep the name in the file; give one if that name is taken here."
              value={name} onChange={(e) => setName(e.currentTarget.value)} />
            <Text size="xs" c="dimmed">Everything in the file is checked first (each file against its checksum); if anything is
              wrong, nothing is created. Firmware images arrive unapproved.</Text>
            <DialogError error={run.error} />
            <Group justify="flex-end">
              <Button variant="default" onClick={reset} data-autofocus>Cancel</Button>
              <Button leftSection={<IconFileImport size={16} />} disabled={!file} loading={run.isPending}
                onClick={() => run.mutate(undefined, { onSuccess: setDone })}>Import</Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

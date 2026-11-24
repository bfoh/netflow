import { Alert, Button, Checkbox, FileInput, Group, List, Modal, Stack, Text, TextInput } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconFileImport, IconLock } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { useAction } from '../../hooks/queries';
import { api, type SystemImport } from '../../services/api';

/** Export a system to one .undm file (D-087): no passwords, files as written. */
export function ExportSystemButton({ projectId }: { projectId: string }) {
  const [opened, { open, close }] = useDisclosure();
  const [firmware, setFirmware] = useState(false);
  const run = useAction(() => api.exportSystem(projectId, firmware), (name) => `Saved ${name} to your downloads`, { errorInDialog: true });
  return (
    <>
      <Button variant="default" leftSection={<IconDownload size={16} />} onClick={open}>Export…</Button>
      <Modal opened={opened} onClose={close} title="Export this system">
        <Stack>
          <Text size="sm">One <code>.undm</code> file with the system's settings, its devices, the names of its logins, its
            configuration files and its topology. A colleague imports it on their copy of UNDM.</Text>
          <Alert color="orange" icon={<IconLock size={16} />} p="xs">
            <Text size="xs">Passwords are never exported: the logins arrive empty. But the team's configuration files are
              included as written, and they can hold passwords (for example Black Box files). Keep the file confidential,
              as you keep those files.</Text>
          </Alert>
          <Checkbox label="Include the approved firmware images for these devices (a much larger file)"
            checked={firmware} onChange={(e) => setFirmware(e.currentTarget.checked)} />
          <DialogError error={run.error} />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Back</Button>
            <Button leftSection={<IconDownload size={16} />} loading={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: close })}>Export</Button>
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
              <Alert color="blue" p="xs" title="Next: store the passwords">
                <Text size="xs" mb={4}>These logins came without passwords. Open the system, Logins tab, and set each one:</Text>
                <List size="xs">{done.summary.logins.map((l) => <List.Item key={l}>{l}</List.Item>)}</List>
              </Alert>
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={reset}>Close</Button>
              <Button onClick={() => { const id = done.project.id; reset(); void navigate(`/projects/${id}`); }}>Open the system</Button>
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
              <Button variant="default" onClick={reset}>Back</Button>
              <Button leftSection={<IconFileImport size={16} />} disabled={!file} loading={run.isPending}
                onClick={() => run.mutate(undefined, { onSuccess: setDone })}>Import</Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

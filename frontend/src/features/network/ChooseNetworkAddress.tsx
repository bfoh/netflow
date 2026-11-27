import { Button, Group, Modal, Radio, Stack, Text, TextInput } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { DialogError } from '../../components/ConfirmDialog';
import { Hint } from '../../components/Hint';
import { Notice } from '../../components/Notice';
import { LoadingLines } from '../../components/Page';
import { Tag } from '../../components/Badges';
import { useAction } from '../../hooks/queries';
import { api } from '../../services/api';
import type { Device, FileAddressCandidate, FileAddresses } from '../../types/api';

const keyOf = (a: FileAddressCandidate) => `${a.address}|${a.version_id}|${a.line}`;
const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;

/**
 * The device's network address (D-125): the addresses its file gives it, read offline, with
 * the one UNDM suggests; the person confirms one or types it. Nothing is sent to the device.
 */
export function ChooseNetworkAddress({ device, opened, onClose }: { device: Device; opened: boolean; onClose: () => void }) {
  const found = useQuery({ queryKey: ['file-addresses', device.id], queryFn: () => api.fileAddresses(device.id), enabled: opened });
  return (
    <Modal opened={opened} onClose={onClose} title={`Network address of ${device.name}`} size="lg">
      <Stack>
        <Text size="sm">The address it has in the network after staging, reached through the BFW. UNDM reads the
          addresses its file gives it; you confirm the right one. Its bench address ({device.management_address || 'none'}) is kept.</Text>
        {found.isLoading && <LoadingLines lines={3} />}
        {found.error && <Notice kind="error" compact>{found.error.message}</Notice>}
        {found.data && <Choose key={device.id} device={device} data={found.data} onClose={onClose} />}
        {!found.data && <Group justify="flex-end"><Button variant="default" onClick={onClose} data-autofocus>Cancel</Button></Group>}
      </Stack>
    </Modal>
  );
}

function Choose({ device, data, onClose }: { device: Device; data: FileAddresses; onClose: () => void }) {
  const initial = data.addresses.find((a) => a.address === device.network_address)
    ?? data.addresses.find((a) => a.address === data.suggested);
  const [choice, setChoice] = useState<string | null>(initial ? keyOf(initial) : null);
  const [typed, setTyped] = useState(initial ? '' : device.network_address ?? '');
  const chosen = data.addresses.find((a) => keyOf(a) === choice);
  const address = typed.trim() || chosen?.address || '';
  const save = useAction((body: { address: string | null; file?: string; line?: number }) => api.setNetworkAddress(device.id, body),
    (d) => (d.network_address ? `${device.name}: network address ${d.network_address}` : `${device.name}: network address cleared`),
    { errorInDialog: true });
  return (
    <>
      {data.files.length === 0
        ? <Hint>It has no file in UNDM yet: type its address.</Hint>
        : <Text size="sm" c="dimmed">Read from {data.files.map((f) => f.name).join(', then ')}
          {data.files[0]?.loaded ? ' (the files UNDM loaded on it).' : ' (its latest file; UNDM did not load it).'}</Text>}
      {data.addresses.length > 0 && (
        <Radio.Group label="Addresses its file gives it" value={choice} onChange={(v) => { setChoice(v); setTyped(''); }}>
          <Stack gap="xs" mt="xs">
            {data.addresses.map((a) => (
              <Radio key={keyOf(a)} value={keyOf(a)}
                label={<Group gap={6}><Text size="sm" ff="monospace">{a.address}{a.prefix !== null ? `/${a.prefix}` : ''}</Text>
                  <Text size="sm">{a.where}</Text>
                  {a.on_bench && <Tag tone="neutral" size="sm">bench</Tag>}
                  {a.address === data.suggested && <Tag tone="info" size="sm">suggested</Tag>}</Group>}
                description={[`${a.file}, line ${a.line}`, a.vdom ? `VDOM ${a.vdom}` : '', a.allows ? `allows ${a.allows}` : '']
                  .filter(Boolean).join(' · ')} />
            ))}
          </Stack>
        </Radio.Group>
      )}
      {data.files.length > 0 && <Text size="sm" c="dimmed">{data.suggested ? `Suggested: ${data.suggested}. ${data.reason}` : data.reason}</Text>}
      <TextInput label={data.addresses.length ? 'Or type it' : 'Its network address'} placeholder="for example 198.51.100.10" value={typed}
        onChange={(e) => setTyped(e.currentTarget.value)}
        error={typed.trim() && !IPV4.test(typed.trim()) ? 'One IPv4 address, for example 198.51.100.10' : undefined} />
      {data.managers.length > 0 && (
        <Notice kind={data.pc_allowed === false ? 'caution' : 'settled'} compact live={false}
          title={data.pc_allowed === false ? 'This PC is outside the limits its file sets' : 'Its file limits who may manage it'}>
          Allowed: {data.managers.map((m) => m.text).join('; ')}.
          {data.pc_address && <> This PC's address towards it now: <b>{data.pc_address}</b>
            {data.pc_allowed === false ? ': the device will refuse UNDM and the SSH window from here.' : '.'}</>}
        </Notice>
      )}
      <DialogError error={save.error} />
      <Group justify="space-between">
        <Button variant="subtle" color="red" disabled={!device.network_address} loading={save.isPending && !save.variables?.address}
          onClick={() => save.mutate({ address: null }, { onSuccess: onClose })}>Clear it</Button>
        <Group>
          <Button variant="default" onClick={onClose} data-autofocus>Cancel</Button>
          <Button disabled={!address || (!!typed.trim() && !IPV4.test(typed.trim()))} loading={save.isPending && !!save.variables?.address}
            onClick={() => save.mutate(typed.trim() || !chosen ? { address } : { address: chosen.address, file: chosen.file, line: chosen.line },
              { onSuccess: onClose })}>Use {address || 'this address'}</Button>
        </Group>
      </Group>
    </>
  );
}

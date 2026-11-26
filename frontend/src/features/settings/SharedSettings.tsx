import { Button, Card, Group, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';

import { Hint } from '../../components/Hint';
import { useAction, useLoginDefaults, useSharedCertificate, useSharedLogins } from '../../hooks/queries';
import { api } from '../../services/api';
import type { LoginDefaults } from '../../types/api';
import { CredentialsPanel } from '../devices/CredentialsPanel';
import { CertificateForm } from './CertificateForm';
import { PciTableCard } from './PciTableCard';
import { BringLoginsIn } from './BringLoginsIn';
import { TemplatesCard } from './TemplatesCard';

const EMPTY: LoginDefaults = {
  firewall: { login: null, login_after: null, tunnel_key: null },
  blackbox: { login: null, login_after: null },
  aruba: { login: null, current: null },
  modem: { login: null },
};

/** Which login each kind of device starts with in Stage a system and the console setup. */
function DefaultLogins() {
  const stored = useLoginDefaults();
  // Stored defaults from before v94 have no modem row: it starts empty (D-124).
  const initial = stored.data?.firewall ? { ...EMPTY, ...stored.data, modem: { ...EMPTY.modem, ...stored.data.modem } } : EMPTY;
  return <DefaultLoginsForm key={JSON.stringify(stored.data ?? null)} initial={initial} />;
}

function DefaultLoginsForm({ initial }: { initial: LoginDefaults }) {
  const logins = useSharedLogins();
  const [form, setForm] = useState<LoginDefaults>(initial);
  const save = useAction((d: LoginDefaults) => api.setLoginDefaults(d), 'Default logins saved');
  const data = (logins.data ?? []).map((r) => ({ value: r.id, label: r.name }));
  const pick = <K extends keyof LoginDefaults>(kind: K, field: keyof LoginDefaults[K], label: string, description?: string) => (
    <Select size="sm" label={label} description={description} clearable data={data}
      placeholder={data.length ? 'None' : 'Add logins above first'}
      value={(form[kind][field] as string | null) ?? null}
      onChange={(v) => setForm({ ...form, [kind]: { ...form[kind], [field]: v } })} />
  );
  return (
    <Card withBorder>
      <Title order={2} mb={4}>Default logins per device</Title>
      <Text size="sm" c="dimmed" mb="sm">
        Stage a system starts each device with these; every choice can still be changed for one device.
      </Text>
      <Stack gap="md">
        <div>
          <Title order={3} mb={4}>FortiGate 101F</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            {pick('firewall', 'login', 'Its login', 'The approved login; its first login sets it on a new unit')}
            {pick('firewall', 'login_after', 'Login after loading', 'The login with the password its base file sets')}
            {pick('firewall', 'tunnel_key', 'Tunnel key', 'Sent for the site file’s secret setting')}
          </SimpleGrid>
        </div>
        <div>
          <Title order={3} mb={4}>Black Box LIG1014A</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            {pick('blackbox', 'login', 'Its login', 'A new unit: admin with no password')}
            {pick('blackbox', 'login_after', 'Login after loading', 'Its team file sets the approved password')}
          </SimpleGrid>
        </div>
        <div>
          <Title order={3} mb={4}>Aruba 2930F (both switches)</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            {pick('aruba', 'login', 'Its login', 'The approved login the console setup gives it')}
            {pick('aruba', 'current', 'Login it has now (console setup)', 'Factory or preconfigured login')}
          </SimpleGrid>
        </div>
        <div>
          <Title order={3} mb={4}>Nokia 7705 SAR-Hmc (modem)</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            {pick('modem', 'login', 'Its login', 'The approved login, user name admin; its first access sets it')}
          </SimpleGrid>
        </div>
        <Group justify="flex-end">
          <Button loading={save.isPending} onClick={() => save.mutate(form)}>Save default logins</Button>
        </Group>
      </Stack>
    </Card>
  );
}

function SharedCertificate() {
  const cert = useSharedCertificate();
  const save = useAction((s: Parameters<typeof api.setSharedCertificate>[0]) => api.setSharedCertificate(s),
    (r) => (r.subject ? 'Certificate answers saved for all systems' : 'Certificate answers removed'));
  return (
    <Card withBorder>
      <Title order={2} mb={4}>HTTPS certificate (Aruba 2930F)</Title>
      <Text size="sm" c="dimmed" mb="sm">
        Before loading a 2930F file that makes the web interface HTTPS-only, UNDM creates the self-signed certificate with
        your team's commands and answers the switch's questions with these values, for every system. A system can still use
        its own answers (its System settings tab). Stored only in this UNDM database.
      </Text>
      {cert.data && <CertificateForm key={cert.data.subject?.common_name ?? 'none'} value={cert.data.subject} saving={save.isPending}
        onSave={(s) => save.mutate(s)} />}
    </Card>
  );
}

/** Settings → Logins (D-105, D-120): the logins every system uses, bringing in a system's own
 *  logins, and which login each kind of device starts with. */
export function LoginSettings() {
  return (
    <Stack>
      <Hint>Every system uses these logins: set them once here. A system can still have its own login for a device that differs.</Hint>
      <Card withBorder>
        <Title order={2} mb="sm">Logins for all systems</Title>
        <CredentialsPanel />
      </Card>
      <BringLoginsIn />
      <DefaultLogins />
    </Stack>
  );
}

/** Settings → Templates: the team's files by zone and the PCI table. */
export function TemplateSettings() {
  return (
    <Stack>
      <Hint>Stage a system generates each device's file from these templates for the system's zone.</Hint>
      <TemplatesCard />
      <PciTableCard />
    </Stack>
  );
}

/** Settings → Certificate: the 2930F HTTPS certificate answers for every system. */
export function CertificateSettings() {
  return <SharedCertificate />;
}

import { Button, Group, SimpleGrid, Stack, TextInput } from '@mantine/core';
import { useState } from 'react';

import type { CertificateSubject } from '../../types/api';

const EMPTY_SUBJECT: CertificateSubject = {
  common_name: '', org_unit: '', org_name: '', locality: '', state: '', country: '',
  profile_name: 'Profile', certificate_name: 'certificate',
};

/** The answers UNDM gives to the 2930F's certificate questions before loading an HTTPS-only
 *  file: for all systems (Settings) or for one system that differs. */
export function CertificateForm({ value, onSave, saving, saveLabel = 'Save certificate answers', removeLabel = 'Remove' }: {
  value: CertificateSubject | null; onSave: (s: CertificateSubject | null) => void; saving: boolean;
  saveLabel?: string; removeLabel?: string;
}) {
  const [form, setForm] = useState<CertificateSubject>(value ?? EMPTY_SUBJECT);
  const field = (key: keyof CertificateSubject, label: string, extra: Record<string, unknown> = {}) => (
    <TextInput label={label} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.currentTarget.value })} {...extra} />
  );
  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {field('common_name', 'Common Name (CN)', { required: true })}
        {field('org_unit', 'Org Unit (OU)')}
        {field('org_name', 'Org Name (O)')}
        {field('locality', 'Locality (L)')}
        {field('state', 'State (ST)')}
        {field('country', 'Country (C)', { description: 'Two letters, or empty', maxLength: 2 })}
        {field('profile_name', 'Identity profile name')}
        {field('certificate_name', 'Certificate name')}
      </SimpleGrid>
      <Group justify="space-between">
        <Button variant="subtle" color="red" disabled={!value} loading={saving} onClick={() => onSave(null)}>{removeLabel}</Button>
        <Button loading={saving} disabled={!form.common_name.trim()} onClick={() => onSave(form)}>{saveLabel}</Button>
      </Group>
    </Stack>
  );
}

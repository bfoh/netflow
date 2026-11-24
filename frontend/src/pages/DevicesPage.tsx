import { Group, Select, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';

import { PageHeader, QueryState } from '../components/Page';
import { DeviceTable } from '../features/devices/DeviceTable';
import { useAllDevices, useProjects } from '../hooks/queries';

export function DevicesPage() {
  const devices = useAllDevices();
  const projects = useProjects();
  const [q, setQ] = useState('');
  const [vendor, setVendor] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const all = devices.data ?? [];
  const uniq = (xs: string[]) => [...new Set(xs)].sort();
  const needle = q.trim().toLowerCase();
  const shown = all.filter((d) =>
    (!vendor || d.manufacturer === vendor) && (!category || d.category === category)
    && (!needle || [d.name, d.management_address, d.role, d.model, d.site].some((v) => v.toLowerCase().includes(needle))));

  return (
    <>
      <PageHeader title="Devices" description="Every device in every system. To add a device, open its system and choose Add device." />
      <Group mb="md" wrap="wrap">
        <TextInput placeholder="Search name, address, role, model, site" leftSection={<IconSearch size={16} />}
          value={q} onChange={(e) => setQ(e.currentTarget.value)} w={320} aria-label="Search devices" />
        <Select placeholder="All vendors" clearable data={uniq(all.map((d) => d.manufacturer))} value={vendor} onChange={setVendor} aria-label="Vendor filter" w={170} />
        <Select placeholder="All categories" clearable data={uniq(all.map((d) => d.category))} value={category} onChange={setCategory} aria-label="Category filter" w={170} />
      </Group>
      <QueryState isLoading={devices.isLoading} error={devices.error} />
      <DeviceTable devices={shown} showProject projectNames={new Map((projects.data ?? []).map((p) => [p.id, p.name]))} />
    </>
  );
}

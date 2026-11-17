import { Card, Select, Stack, Text } from '@mantine/core';
import { useState } from 'react';

import { EnvironmentBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { ConfigWorkbench } from '../features/configurations/ConfigWorkbench';
import { useAllDevices, useProjects } from '../hooks/queries';

export function ConfigurationsPage() {
  const devices = useAllDevices();
  const projects = useProjects();
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const device = devices.data?.find((d) => d.id === deviceId);
  return (
    <>
      <PageHeader title="Configuration Studio" description="Generate, preview, validate and compare device configurations from vendor-neutral intent." />
      <QueryState isLoading={devices.isLoading} error={devices.error} />
      <Stack>
        <Card withBorder>
          <Select label="Device" searchable placeholder="Choose a network element" maw={480}
            data={(devices.data ?? []).map((d) => ({ value: d.id, label: `${d.name} — ${d.manufacturer} ${d.model} (${names.get(d.project_id) ?? ''})` }))}
            value={deviceId} onChange={setDeviceId} />
          {device && <Text size="sm" mt="xs" component="div"><EnvironmentBadge env={device.environment} /> Driver <code>{device.driver_id}</code></Text>}
        </Card>
        {device && <ConfigWorkbench key={device.id} device={device} />}
      </Stack>
    </>
  );
}

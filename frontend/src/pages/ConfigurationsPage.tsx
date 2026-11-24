import { Anchor, Card, Group, Select, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';

import { EnvironmentBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { ConfigWorkbench } from '../features/configurations/ConfigWorkbench';
import { useAllDevices, useProjects } from '../hooks/queries';
import { driverLabel } from '../services/labels';

export function ConfigurationsPage() {
  const devices = useAllDevices();
  const projects = useProjects();
  const [params] = useSearchParams();
  const [deviceId, setDeviceId] = useState<string | null>(params.get('device'));
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const device = devices.data?.find((d) => d.id === deviceId);
  return (
    <>
      <PageHeader title="Files" description="The configuration files of each device: import your team's files, check them, or generate one from the device's settings." />
      <QueryState isLoading={devices.isLoading} error={devices.error} />
      <Stack>
        <Card withBorder>
          <Select label="Device" searchable placeholder="Choose a device" maw={480}
            data={(devices.data ?? []).map((d) => ({ value: d.id, label: `${d.name} — ${d.manufacturer} ${d.model} (${names.get(d.project_id) ?? ''})` }))}
            value={deviceId} onChange={setDeviceId} />
          {device && (
            <Group mt="xs" gap="md">
              <Text size="sm" component="div"><EnvironmentBadge env={device.environment} /> {driverLabel(device.driver_id)}</Text>
              <Anchor component={Link} to={`/devices/${device.id}`} size="sm">Device page</Anchor>
              <Anchor component={Link} to={`/deployments?project=${device.project_id}&devices=${device.id}`} size="sm">Make a plan for this device</Anchor>
            </Group>
          )}
        </Card>
        {device && <ConfigWorkbench key={device.id} device={device}
          initialVersion={device.id === params.get('device') ? params.get('version') : null} />}
      </Stack>
    </>
  );
}

import { Card, Group, Select, Stack, Text } from '@mantine/core';
import { useSearchParams } from 'react-router';

import { EnvironmentBadge } from '../components/Badges';
import { PageHeader, QueryState } from '../components/Page';
import { CONSOLE_PLATFORMS } from '../features/provisioning/consolePlatforms';
import { ConsoleSetup } from '../features/provisioning/ConsoleSetup';
import { useAllDevices, useDrivers, useProjects } from '../hooks/queries';
import { driverLabel, stateLabel } from '../services/labels';

export function ProvisioningPage() {
  const [params, setParams] = useSearchParams();
  const devices = useAllDevices();
  const drivers = useDrivers();
  const projects = useProjects();
  const platform = new Map((drivers.data ?? []).map((d) => [d.driver_id, d]));
  const eligible = (devices.data ?? []).filter((d) => CONSOLE_PLATFORMS.has(platform.get(d.driver_id)?.platform ?? ''));
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const deviceId = params.get('device');
  const device = eligible.find((d) => d.id === deviceId);

  return (
    <>
      <PageHeader title="Console setup"
        description="Through the console cable: give a new Aruba switch its first address and login, or a Nokia modem from the factory its first access." />
      <QueryState isLoading={devices.isLoading || drivers.isLoading} error={devices.error ?? drivers.error} />
      <Stack>
        <Card withBorder>
          <Select label="Device" w="100%" maw={520} searchable
            placeholder={eligible.length ? 'Choose a device' : 'No Aruba 2930F or Nokia modem in your systems yet'}
            data={eligible.map((d) => ({ value: d.id, label: `${d.name} — ${d.manufacturer} ${d.model} (${names.get(d.project_id) ?? ''})` }))}
            value={device?.id ?? null} onChange={(v) => setParams(v ? { device: v } : {})} />
          {device && <Group gap="xs" mt="xs"><EnvironmentBadge env={device.environment} /><Text size="sm">{driverLabel(device.driver_id, drivers.data)} · setup: {stateLabel(device.provisioning_status).toLowerCase()}</Text></Group>}
          <Text size="xs" c="dimmed" mt="xs">
            Only devices that need the console are listed: Aruba 2930F (ArubaOS-Switch), new or preconfigured (it can
            be erased first), and the Nokia 7705 SAR-Hmc modem (its first access). The other devices need none: a new FortiGate answers at its factory address, and a First login
            plan sets its approved password; a new Black Box LIG1014A answers at its factory address with no password.
          </Text>
        </Card>
        {device && <ConsoleSetup device={device} />}
      </Stack>
    </>
  );
}

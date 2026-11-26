import {
  Anchor, Button, Card, type MantineColorScheme, SegmentedControl, Group, Stack, Table, Tabs, Text, TextInput, Title,
  useMantineColorScheme,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useQuery } from '@tanstack/react-query';

import { useState } from 'react';
import { useSearchParams } from 'react-router';

import { Tag } from '../components/Badges';
import { DataTable } from '../components/DataTable';
import { PageHeader } from '../components/Page';
import { useDeviceModels, useDrivers } from '../hooks/queries';
import { api, getActor, setActor } from '../services/api';
import { SafetyPanel } from '../features/settings/SafetyPanel';
import { CertificateSettings, LoginSettings, TemplateSettings } from '../features/settings/SharedSettings';
import { capabilityLabel, driverLabel, humanize, stateLabel } from '../services/labels';
import { Hint } from '../components/Hint';
import type { SettingsTab } from '../paths';

const SUPPORT: Record<string, string> = {
  simulated_only: 'Simulated only', lab_read_only: 'Checked on real hardware', lab_validated: 'Validated on real hardware',
};

const TABS = ['logins', 'templates', 'certificate', 'safety', 'identity', 'about'] as const;
/** Tab names before D-120 open the tab that now holds their content. */
const OLD_TABS: Record<string, SettingsTab> = { shared: 'logins', models: 'about', drivers: 'about', system: 'about' };
function tabOf(value: string | null): SettingsTab {
  if (value && (TABS as readonly string[]).includes(value)) return value as SettingsTab;
  return (value && OLD_TABS[value]) || 'logins';
}

/** Light, dark, or as Windows is set; remembered in this browser (D-119). */
function Appearance() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  return (
    <Card maw={560} mt="md">
      <Stack gap="xs">
        <Title order={2}>Appearance</Title>
        <SegmentedControl aria-label="Appearance" value={colorScheme} onChange={(v) => setColorScheme(v as MantineColorScheme)}
          data={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }, { value: 'auto', label: 'As Windows is set' }]} />
        <Text size="xs" c="dimmed">The button with the moon or sun at the top right switches between light and dark too.</Text>
      </Stack>
    </Card>
  );
}

export function SettingsPage() {
  const drivers = useDrivers();
  const models = useDeviceModels();
  const health = useQuery({ queryKey: ['health'], queryFn: api.health });
  const [actor, setActorState] = useState(getActor());
  const [params, setParams] = useSearchParams();
  const tab = tabOf(params.get('tab'));
  return (
    <>
      <PageHeader title="Settings" description="What every system uses (logins, templates, certificate), the safety switches, your name, and this copy of UNDM." />
      <Tabs value={tab} onChange={(v) => setParams(v ? { tab: v } : {}, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="logins">Logins</Tabs.Tab>
          <Tabs.Tab value="templates">Templates</Tabs.Tab>
          <Tabs.Tab value="certificate">Certificate</Tabs.Tab>
          <Tabs.Tab value="safety">Safety</Tabs.Tab>
          <Tabs.Tab value="identity">Your name and appearance</Tabs.Tab>
          <Tabs.Tab value="about">About</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="logins"><LoginSettings /></Tabs.Panel>
        <Tabs.Panel value="templates"><TemplateSettings /></Tabs.Panel>
        <Tabs.Panel value="certificate"><CertificateSettings /></Tabs.Panel>
        <Tabs.Panel value="safety"><SafetyPanel /></Tabs.Panel>
        <Tabs.Panel value="identity">
          <Card maw={560}>
            <Stack>
              <Hint>
                Your name is written in the audit log next to everything you do, and a second person approving a plan is
                told apart by it. It is not a login: UNDM has no user accounts yet, so use it only on your own PC.
              </Hint>
              <TextInput label="Your name" value={actor} onChange={(e) => setActorState(e.currentTarget.value)} />
              <Group><Button onClick={() => { setActor(actor.trim() || 'local-user'); notifications.show({ message: 'Saved. Reloading…' }); window.location.reload(); }}>Save</Button></Group>
            </Stack>
          </Card>
          <Appearance />
        </Tabs.Panel>
        <Tabs.Panel value="about">
          <Stack gap="lg">
            <Card maw={560}>
              <Table aria-label="This copy of UNDM"><Table.Tbody>
                <Table.Tr><Table.Th scope="row" w={180}>Status</Table.Th><Table.Td>{health.data?.status ? stateLabel(health.data.status) : (health.error ? 'UNDM is not answering' : '…')}</Table.Td></Table.Tr>
                <Table.Tr><Table.Th scope="row">Version</Table.Th><Table.Td>{health.data?.version ?? '—'}</Table.Td></Table.Tr>
              </Table.Tbody></Table>
            </Card>
            <Stack gap="sm">
              <Title order={2}>For engineers</Title>
              <Hint>
                The device models UNDM knows and the drivers that connect to them. Listing a model is not a compatibility
                claim: “Simulated only” means no real-device driver exists or has been validated. The programming
                interface is described in the <Anchor href="/api/docs" target="_blank" rel="noreferrer" size="xs">API documentation</Anchor>.
              </Hint>
              <Title order={3}>Device models</Title>
              <Card padding={0}>
                <DataTable label="Device models" loading={models.isLoading} error={models.error} rowCount={models.data?.length ?? 0}
                  empty="No device models are known." minWidth={640} highlight={false}>
                  <Table.Thead><Table.Tr><Table.Th>Model</Table.Th><Table.Th>Category</Table.Th><Table.Th>OS</Table.Th><Table.Th>Connects by</Table.Th><Table.Th>Support</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {(models.data ?? []).map((m) => (
                      <Table.Tr key={m.model_id}>
                        <Table.Td>{m.manufacturer} {m.model}</Table.Td><Table.Td>{humanize(m.category)}</Table.Td><Table.Td>{m.os_family}</Table.Td>
                        <Table.Td><Text size="sm">{m.drivers.map((x) => driverLabel(x, drivers.data)).join(' · ')}</Text></Table.Td>
                        <Table.Td><Tag tone={m.support === 'simulated_only' ? 'simulated' : 'success'}>{SUPPORT[m.support] ?? humanize(m.support)}</Tag></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </DataTable>
              </Card>
              <Title order={3}>Drivers</Title>
              <Card padding={0}>
                <DataTable label="Drivers" loading={drivers.isLoading} error={drivers.error} rowCount={drivers.data?.length ?? 0}
                  empty="No drivers are installed." minWidth={760} highlight={false}>
                  <Table.Thead><Table.Tr><Table.Th>Connects to</Table.Th><Table.Th>Vendor / OS</Table.Th><Table.Th>Kind</Table.Th><Table.Th>What it can do</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {(drivers.data ?? []).map((d) => (
                      <Table.Tr key={d.driver_id}>
                        <Table.Td><Text size="sm" fw={600}>{driverLabel(d.driver_id, drivers.data)}</Text><Text size="xs" c="dimmed">{d.description}</Text><Text size="xs" c="dimmed" ff="monospace">{d.driver_id}</Text></Table.Td>
                        <Table.Td>{d.vendor} · {d.os_family}</Table.Td>
                        <Table.Td><Tag tone={d.simulated ? 'simulated' : 'warning'}>{d.simulated ? 'Simulated' : d.maturity === 'experimental' ? 'Real · experimental' : 'Real · proven'}</Tag></Table.Td>
                        <Table.Td><Group gap={4}>{d.capabilities.map((c) => <Tag key={c}>{capabilityLabel(c)}</Tag>)}</Group></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </DataTable>
              </Card>
            </Stack>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </>
  );
}

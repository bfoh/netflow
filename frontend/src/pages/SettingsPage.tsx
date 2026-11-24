import { Badge, Button, Card, Group, Stack, Table, Tabs, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useQuery } from '@tanstack/react-query';

import { useState } from 'react';

import { PageHeader } from '../components/Page';
import { useDeviceModels, useDrivers } from '../hooks/queries';
import { api, getActor, setActor } from '../services/api';
import { SafetyPanel } from '../features/settings/SafetyPanel';
import { capabilityLabel, driverLabel, humanize, stateLabel } from '../services/labels';
import { Hint } from '../components/Hint';

const SUPPORT: Record<string, string> = {
  simulated_only: 'Simulated only', lab_read_only: 'Checked on real hardware', lab_validated: 'Validated on real hardware',
};

export function SettingsPage() {
  const drivers = useDrivers();
  const models = useDeviceModels();
  const health = useQuery({ queryKey: ['health'], queryFn: api.health });
  const [actor, setActorState] = useState(getActor());
  return (
    <>
      <PageHeader title="Settings" description="Safety switches, your name for the audit log, supported models and information about this copy of UNDM." />
      <Tabs defaultValue="safety" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="safety">Safety</Tabs.Tab>
          <Tabs.Tab value="identity">Your name</Tabs.Tab>
          <Tabs.Tab value="models">Device models</Tabs.Tab>
          <Tabs.Tab value="drivers">Drivers</Tabs.Tab>
          <Tabs.Tab value="system">About</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="safety"><SafetyPanel /></Tabs.Panel>
        <Tabs.Panel value="identity">
          <Card withBorder maw={560}>
            <Stack>
              <Hint>
                Your name is written in the audit log next to everything you do, and a second person approving a plan is
                told apart by it. It is not a login: UNDM has no user accounts yet, so use it only on your own PC.
              </Hint>
              <TextInput label="Your name" value={actor} onChange={(e) => setActorState(e.currentTarget.value)} />
              <Group><Button onClick={() => { setActor(actor.trim() || 'local-user'); notifications.show({ message: 'Saved. Reloading…' }); window.location.reload(); }}>Save</Button></Group>
            </Stack>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="drivers">
          <Card withBorder padding={0}>
            <Table.ScrollContainer minWidth={760}>
              <Table verticalSpacing="sm" horizontalSpacing="md">
                <Table.Thead><Table.Tr><Table.Th>Connects to</Table.Th><Table.Th>Vendor / OS</Table.Th><Table.Th>Kind</Table.Th><Table.Th>What it can do</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {(drivers.data ?? []).map((d) => (
                    <Table.Tr key={d.driver_id}>
                      <Table.Td><Text size="sm" fw={600}>{driverLabel(d.driver_id, drivers.data)}</Text><Text size="xs" c="dimmed">{d.description}</Text><Text size="xs" c="dimmed" ff="monospace">{d.driver_id}</Text></Table.Td>
                      <Table.Td>{d.vendor} · {d.os_family}</Table.Td>
                      <Table.Td><Badge color={d.simulated ? 'violet' : 'orange'} variant="light">{d.simulated ? 'Simulated' : d.maturity === 'experimental' ? 'Real · experimental' : 'Real · proven'}</Badge></Table.Td>
                      <Table.Td><Group gap={4}>{d.capabilities.map((c) => <Badge key={c} size="xs" variant="outline" color="gray" tt="none">{capabilityLabel(c)}</Badge>)}</Group></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="models">
          <Card withBorder padding={0}>
            <Table.ScrollContainer minWidth={640}>
              <Table verticalSpacing="sm" horizontalSpacing="md">
                <Table.Thead><Table.Tr><Table.Th>Model</Table.Th><Table.Th>Category</Table.Th><Table.Th>OS</Table.Th><Table.Th>Connects by</Table.Th><Table.Th>Support</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {(models.data ?? []).map((m) => (
                    <Table.Tr key={m.model_id}>
                      <Table.Td>{m.manufacturer} {m.model}</Table.Td><Table.Td>{humanize(m.category)}</Table.Td><Table.Td>{m.os_family}</Table.Td>
                      <Table.Td><Text size="xs">{m.drivers.map((x) => driverLabel(x, drivers.data)).join(' · ')}</Text></Table.Td>
                      <Table.Td><Badge variant="light" color={m.support === 'simulated_only' ? 'violet' : 'teal'}>{SUPPORT[m.support] ?? humanize(m.support)}</Badge></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
          <Text size="xs" c="dimmed" mt="xs">Listing a model is not a compatibility claim. “Simulated only” means no real-device driver exists or has been validated.</Text>
        </Tabs.Panel>
        <Tabs.Panel value="system">
          <Card withBorder maw={560}>
            <Table><Table.Tbody>
              <Table.Tr><Table.Td c="dimmed">Status</Table.Td><Table.Td>{health.data?.status ? stateLabel(health.data.status) : (health.error ? 'UNDM is not answering' : '…')}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td c="dimmed">Version</Table.Td><Table.Td>{health.data?.version ?? '—'}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td c="dimmed">API documentation</Table.Td><Table.Td><a href="/api/docs" target="_blank" rel="noreferrer">OpenAPI (Swagger UI)</a></Table.Td></Table.Tr>
            </Table.Tbody></Table>
          </Card>
        </Tabs.Panel>
      </Tabs>
    </>
  );
}

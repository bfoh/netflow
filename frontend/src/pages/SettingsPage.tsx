import { Alert, Badge, Button, Card, Group, Stack, Table, Tabs, Text, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useQuery } from '@tanstack/react-query';
import { IconInfoCircle } from '@tabler/icons-react';
import { useState } from 'react';

import { PageHeader } from '../components/Page';
import { useDeviceModels, useDrivers } from '../hooks/queries';
import { api, getActor, setActor } from '../services/api';

export function SettingsPage() {
  const drivers = useDrivers();
  const models = useDeviceModels();
  const health = useQuery({ queryKey: ['health'], queryFn: api.health });
  const [actor, setActorState] = useState(getActor());
  return (
    <>
      <PageHeader title="Settings" description="Session identity, drivers, device model registry and system information." />
      <Tabs defaultValue="identity" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="identity">Identity</Tabs.Tab>
          <Tabs.Tab value="drivers">Drivers</Tabs.Tab>
          <Tabs.Tab value="models">Device models</Tabs.Tab>
          <Tabs.Tab value="system">System</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="identity">
          <Card withBorder maw={560}>
            <Stack>
              <Alert color="yellow" icon={<IconInfoCircle size={16} />}>
                User authentication and role-based access control are not implemented yet. The name below is sent with each
                request to attribute actions in the audit trail; it is not a login. Run the backend on localhost only.
              </Alert>
              <TextInput label="Acting as" value={actor} onChange={(e) => setActorState(e.currentTarget.value)} />
              <Group><Button onClick={() => { setActor(actor.trim() || 'local-user'); notifications.show({ message: 'Saved. Reloading…' }); window.location.reload(); }}>Save</Button></Group>
            </Stack>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="drivers">
          <Card withBorder padding={0}>
            <Table.ScrollContainer minWidth={760}>
              <Table verticalSpacing="sm" horizontalSpacing="md">
                <Table.Thead><Table.Tr><Table.Th>Driver</Table.Th><Table.Th>Vendor / OS</Table.Th><Table.Th>Type</Table.Th><Table.Th>Capabilities</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {(drivers.data ?? []).map((d) => (
                    <Table.Tr key={d.driver_id}>
                      <Table.Td><Text ff="monospace" size="sm">{d.driver_id}</Text><Text size="xs" c="dimmed">{d.description}</Text></Table.Td>
                      <Table.Td>{d.vendor} · {d.os_family}</Table.Td>
                      <Table.Td><Badge color={d.simulated ? 'violet' : 'orange'} variant="light">{d.simulated ? 'simulated' : `real · ${d.maturity}`}</Badge></Table.Td>
                      <Table.Td><Group gap={4}>{d.capabilities.map((c) => <Badge key={c} size="xs" variant="outline" color="gray">{c.replace('supports_', '')}</Badge>)}</Group></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="models">
          <Card withBorder padding={0}>
            <Table verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead><Table.Tr><Table.Th>Model</Table.Th><Table.Th>Category</Table.Th><Table.Th>OS</Table.Th><Table.Th>Drivers</Table.Th><Table.Th>Support</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(models.data ?? []).map((m) => (
                  <Table.Tr key={m.model_id}>
                    <Table.Td>{m.manufacturer} {m.model}</Table.Td><Table.Td>{m.category}</Table.Td><Table.Td>{m.os_family}</Table.Td>
                    <Table.Td><Text ff="monospace" size="xs">{m.drivers.join(', ')}</Text></Table.Td>
                    <Table.Td><Badge variant="light" color="violet">{m.support.replaceAll('_', ' ')}</Badge></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card>
          <Text size="xs" c="dimmed" mt="xs">Listing a model is not a compatibility claim. “Simulated only” means no real-device driver exists or has been validated.</Text>
        </Tabs.Panel>
        <Tabs.Panel value="system">
          <Card withBorder maw={560}>
            <Table><Table.Tbody>
              <Table.Tr><Table.Td c="dimmed">Backend status</Table.Td><Table.Td>{health.data?.status ?? (health.error ? 'unreachable' : '…')}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td c="dimmed">Backend version</Table.Td><Table.Td>{health.data?.version ?? '—'}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td c="dimmed">API documentation</Table.Td><Table.Td><a href="/api/docs" target="_blank" rel="noreferrer">OpenAPI (Swagger UI)</a></Table.Td></Table.Tr>
            </Table.Tbody></Table>
          </Card>
        </Tabs.Panel>
      </Tabs>
    </>
  );
}

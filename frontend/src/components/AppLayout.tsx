import { Alert, AppShell, Badge, Burger, Group, NavLink, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconActivity, IconDatabaseExclamation } from '@tabler/icons-react';
import { NavLink as RouterNavLink, Outlet, useLocation } from 'react-router';

import { useHealth, usePolicy } from '../hooks/queries';
import { getActor } from '../services/api';
import { NAV } from './nav';



export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  const policy = usePolicy();
  const health = useHealth();
  const isActive = (to: string) => (to === '/' ? pathname === '/' : pathname.startsWith(to));

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 230, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="lg"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <IconActivity size={22} color="var(--mantine-color-indigo-6)" />
            <Text fw={700}>UNDM</Text>
            <Text c="dimmed" size="sm" visibleFrom="md">Universal Network Deployment Manager</Text>
          </Group>
          <Group gap="sm" wrap="nowrap">
            {policy.data?.enable_real_device_writes ? (
              <Tooltip label="Approved deployments may change real lab devices (UNDM_ENABLE_REAL_DEVICE_WRITES=true)." withArrow>
                <Badge color="red" variant="filled" radius="sm">Real-device changes ON</Badge>
              </Tooltip>
            ) : (
              <Tooltip label="Real devices can only be read. Simulated devices can be fully exercised." withArrow>
                <Badge color="violet" variant="filled" radius="sm">Real-device changes off</Badge>
              </Tooltip>
            )}
            <Text size="sm" c="dimmed" visibleFrom="xs">acting as <b>{getActor()}</b></Text>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs" aria-label="Main navigation">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            component={RouterNavLink}
            to={to}
            label={label}
            leftSection={<Icon size={18} stroke={1.6} />}
            active={isActive(to)}
            onClick={close}
            variant="light"
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        {health.data?.problem && (
          <Alert color="red" icon={<IconDatabaseExclamation size={18} />} mb="md" title="Database upgrade needed">
            {health.data.problem}
          </Alert>
        )}
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

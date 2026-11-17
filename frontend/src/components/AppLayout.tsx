import { AppShell, Badge, Burger, Group, NavLink, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconActivity } from '@tabler/icons-react';
import { NavLink as RouterNavLink, Outlet, useLocation } from 'react-router';

import { getActor } from '../services/api';
import { NAV } from './nav';



export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
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
            <Tooltip label="Only simulated drivers are installed. No physical device can be contacted." withArrow>
              <Badge color="violet" variant="filled" radius="sm">Simulation mode</Badge>
            </Tooltip>
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
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

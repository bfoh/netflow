import { AppShell, Burger, Code, Group, NavLink, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconActivity, IconTool } from '@tabler/icons-react';
import { NavLink as RouterNavLink, Outlet, useLocation } from 'react-router';

import { useHealth } from '../hooks/queries';
import { getActor } from '../services/api';
import { ADVANCED_NAV, NAV, SETTINGS_NAV } from './nav';
import { Notice } from './Notice';


export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
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
            <Text size="sm" c="dimmed" visibleFrom="xs">acting as <b>{getActor()}</b></Text>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs" aria-label="Main navigation">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} component={RouterNavLink} to={to} label={label}
            leftSection={<Icon size={18} stroke={1.6} />} active={isActive(to)} onClick={close} variant="light" />
        ))}
        <NavLink label="Advanced" leftSection={<IconTool size={18} stroke={1.6} />}
          defaultOpened={ADVANCED_NAV.some(({ to }) => isActive(to))} variant="light">
          {ADVANCED_NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} component={RouterNavLink} to={to} label={label}
              leftSection={<Icon size={16} stroke={1.6} />} active={isActive(to)} onClick={close} variant="light" />
          ))}
        </NavLink>
        <NavLink component={RouterNavLink} to={SETTINGS_NAV.to} label={SETTINGS_NAV.label} mt="auto"
          leftSection={<SETTINGS_NAV.icon size={18} stroke={1.6} />} active={isActive(SETTINGS_NAV.to)} onClick={close} variant="light" />
      </AppShell.Navbar>

      <AppShell.Main>
        {health.data?.problem && (
          <Notice kind="error" mb="md" title="UNDM needs a database upgrade before it can be used">
            {health.data.problem}
            <Code block mt={6}>backend\.venv\Scripts\python.exe -m alembic upgrade head</Code>
          </Notice>
        )}
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

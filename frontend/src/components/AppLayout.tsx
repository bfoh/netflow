import { Alert, AppShell, Badge, Burger, Group, NavLink, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconActivity, IconDatabaseExclamation, IconTool } from '@tabler/icons-react';
import { NavLink as RouterNavLink, Outlet, useLocation } from 'react-router';

import { useHealth, usePolicy } from '../hooks/queries';
import { getActor } from '../services/api';
import { ADVANCED_NAV, NAV, SETTINGS_NAV } from './nav';


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
            <Tooltip withArrow multiline w={300} label={policy.data?.enable_real_device_writes
              ? 'Approved plans may change real devices on the bench.'
              : 'Real devices can only be read. Simulated devices can be changed freely.'}>
              <Badge color={policy.data?.enable_real_device_writes ? 'red' : 'gray'} variant={policy.data?.enable_real_device_writes ? 'filled' : 'light'} radius="sm">
                Real-device changes {policy.data?.enable_real_device_writes ? 'ON' : 'off'}
              </Badge>
            </Tooltip>
            <Tooltip withArrow multiline w={300} label={policy.data?.enable_real_device_firmware
              ? 'Approved firmware plans may upgrade real devices.'
              : 'Firmware on real devices cannot be changed (dry runs only).'}>
              <Badge color={policy.data?.enable_real_device_firmware ? 'red' : 'gray'} variant={policy.data?.enable_real_device_firmware ? 'filled' : 'light'} radius="sm" visibleFrom="sm">
                Firmware changes {policy.data?.enable_real_device_firmware ? 'ON' : 'off'}
              </Badge>
            </Tooltip>
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
          <Alert color="red" icon={<IconDatabaseExclamation size={18} />} mb="md" title="UNDM needs a database upgrade">
            {health.data.problem}
          </Alert>
        )}
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

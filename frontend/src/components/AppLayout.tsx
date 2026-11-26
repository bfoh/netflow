import { ActionIcon, AppShell, Burger, Code, Group, NavLink, Text, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconActivity, IconMoon, IconSun, IconTool } from '@tabler/icons-react';
import { useEffect, useRef } from 'react';
import { NavLink as RouterNavLink, Outlet, useLocation } from 'react-router';

import { useHealth } from '../hooks/queries';
import { getActor } from '../services/api';
import { ADVANCED_NAV, NAV, SETTINGS_NAV } from './nav';
import { Notice } from './Notice';


/** Light or dark, remembered on this PC (D-119). */
function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light');
  const next = scheme === 'dark' ? 'light' : 'dark';
  return (
    <ActionIcon variant="subtle" color="gray" onClick={() => setColorScheme(next)} aria-label={`Switch to ${next} mode`}>
      {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
    </ActionIcon>
  );
}

/** After moving to another page, keyboard and screen-reader users start at its title
 *  (WCAG 2.4.3); the first page load keeps the browser's own focus. */
function useFocusTitleOnNavigate(pathname: string) {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const t = window.setTimeout(() => document.getElementById('page-title')?.focus({ preventScroll: true }), 50);
    return () => window.clearTimeout(t);
  }, [pathname]);
}

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  const health = useHealth();
  useFocusTitleOnNavigate(pathname);
  const isActive = (to: string) => (to === '/' ? pathname === '/' : pathname.startsWith(to));

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 230, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="lg"
    >
      <a href="#main" className="undm-skip-link">Skip to content</a>
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <IconActivity size={22} color="var(--mantine-primary-color-filled)" aria-hidden />
            <Text fw={700}>UNDM</Text>
            <Text c="dimmed" size="sm" visibleFrom="md">Universal Network Deployment Manager</Text>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <Text size="sm" c="dimmed" visibleFrom="xs">acting as <b>{getActor()}</b></Text>
            <ColorSchemeToggle />
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

      <AppShell.Main id="main" tabIndex={-1} style={{ outline: 'none' }}>
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

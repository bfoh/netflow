import {
  ActionIcon, Anchor, AppShell, Burger, Button, Code, Collapse, CopyButton, Group, NavLink, ScrollArea, Stack, Text,
  UnstyledButton, useComputedColorScheme, useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconActivity, IconChevronDown, IconChevronRight, IconMoon, IconSun } from '@tabler/icons-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router';

import { useHealth } from '../hooks/queries';
import { paths } from '../paths';
import { getActor } from '../services/api';
import { isActivePath, NAV_GROUPS, type NavGroup } from './nav';
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

/** Which sidebar entry a page belongs to. A device page belongs to its system (it is reached
 *  from there), so it lights up Systems; "Devices (all systems)" is the list itself. */
function activeEntry(to: string, pathname: string): boolean {
  if (to === paths.devices) return pathname === paths.devices;
  if (to === paths.systems) return isActivePath(to, pathname) || pathname.startsWith(`${paths.devices}/`);
  return isActivePath(to, pathname);
}

/** One group of the sidebar. A folded group is a real button (aria-expanded), open while one
 *  of its pages is shown, so engineers' pages stay out of the way without being hidden. */
function NavSection({ group, pathname, onNavigate }: { group: NavGroup; pathname: string; onNavigate: () => void }) {
  const id = useId();
  const holdsActive = group.items.some(({ to }) => activeEntry(to, pathname));
  // A group stays open while one of its pages is shown; otherwise the person decides.
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = holdsActive || (toggled ?? !group.folded);
  const items = group.items.map(({ to, label, icon: Icon }) => (
    <NavLink key={to} component={Link} to={to} label={label}
      leftSection={<Icon size={18} stroke={1.6} />} active={activeEntry(to, pathname)}
      aria-current={activeEntry(to, pathname) ? 'page' : undefined} onClick={onNavigate} variant="light" />
  ));
  return (
    <div role="group" aria-labelledby={id}>
      {group.folded ? (
        <UnstyledButton id={id} onClick={() => setToggled(!open)} aria-expanded={open} aria-controls={`${id}-items`}
          px="sm" py={6} w="100%" style={{ borderRadius: 'var(--mantine-radius-sm)' }}>
          <Group gap={6} wrap="nowrap">
            {open ? <IconChevronDown size={14} aria-hidden /> : <IconChevronRight size={14} aria-hidden />}
            <Text size="xs" fw={700} c="dimmed" tt="uppercase">{group.label}</Text>
          </Group>
        </UnstyledButton>
      ) : (
        <Text id={id} size="xs" fw={700} c="dimmed" tt="uppercase" px="sm" pt={6} pb={4}>{group.label}</Text>
      )}
      {group.folded ? <Collapse expanded={open}><div id={`${id}-items`}>{items}</div></Collapse> : items}
    </div>
  );
}

/** The database is older than this UNDM: say it plainly; the exact command is one click away. */
function DatabaseUpgrade({ problem }: { problem: string }) {
  const command = 'backend\\.venv\\Scripts\\python.exe -m alembic upgrade head';
  return (
    <Notice kind="error" mb="md" title="UNDM needs a database upgrade before it can be used"
      details={<Stack gap={6}>
        <Text size="xs">{problem}</Text>
        <Group gap="xs" wrap="nowrap" align="flex-start">
          <Code block style={{ flex: 1 }}>{command}</Code>
          <CopyButton value={command}>
            {({ copied, copy }) => <Button size="xs" variant="default" onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>}
          </CopyButton>
        </Group>
      </Stack>}>
      Stop UNDM, run the upgrade command in the undm folder (under More), then start UNDM again. Your data is kept.
    </Notice>
  );
}

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  const health = useHealth();
  useFocusTitleOnNavigate(pathname);

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !opened } }}
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
            <Text size="sm" c="dimmed" visibleFrom="xs">
              Acting as <Anchor component={Link} to={paths.settings('identity')} size="sm" fw={600}>{getActor()}</Anchor>
            </Text>
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs" aria-label="Main navigation">
        <AppShell.Section grow component={ScrollArea}>
          <Stack gap="sm">
            {NAV_GROUPS.map((g) => <NavSection key={g.label} group={g} pathname={pathname} onNavigate={close} />)}
          </Stack>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main id="main" tabIndex={-1} style={{ outline: 'none' }}>
        {health.data?.problem && <DatabaseUpgrade problem={health.data.problem} />}
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

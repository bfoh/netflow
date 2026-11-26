import {
  IconBinaryTree2, IconCpu, IconFolders, IconHistory, IconHome, IconListCheck,
  IconRocket, IconRouter, IconSettings, IconUpload,
} from '@tabler/icons-react';

import { paths } from '../paths';

export interface NavItem { to: string; label: string; icon: typeof IconHome }
export interface NavGroup { label: string; items: NavItem[]; folded?: boolean }

/**
 * The sidebar (D-120), in three groups: the work technicians do, what is set up once, and
 * the engineers' pages, folded away until one of them is open.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Work',
    items: [
      { to: paths.home, label: 'Home', icon: IconHome },
      { to: paths.stage(), label: 'Stage a system', icon: IconListCheck },
      { to: paths.systems, label: 'Systems', icon: IconFolders },
    ],
  },
  {
    label: 'Setup',
    items: [
      { to: paths.firmware(), label: 'Firmware', icon: IconUpload },
      { to: paths.settings(), label: 'Settings', icon: IconSettings },
    ],
  },
  {
    label: 'Advanced',
    folded: true,
    items: [
      { to: paths.devices, label: 'Devices (all systems)', icon: IconRouter },
      { to: paths.plans, label: 'Plans', icon: IconRocket },
      { to: paths.console(), label: 'Console tool', icon: IconCpu },
      { to: paths.topology, label: 'Topology', icon: IconBinaryTree2 },
      { to: paths.audit, label: 'Audit log', icon: IconHistory },
    ],
  },
];

/** A sidebar entry is active on its own page and the pages below it, never on a page that
 *  merely starts with the same letters (/plans is not /plans-old). */
export function isActivePath(to: string, pathname: string): boolean {
  if (to === '/') return pathname === '/';
  return pathname === to || pathname.startsWith(`${to}/`);
}

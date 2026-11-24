import {
  IconBinaryTree2, IconCpu, IconFileCode, IconFolders, IconHistory, IconHome, IconListCheck,
  IconRocket, IconRouter, IconSettings, IconUpload,
} from '@tabler/icons-react';

/** Main navigation, in the order of the work: systems and devices, their files and firmware,
 * the console setup of new switches, then the plans that change devices. */
export const NAV = [
  { to: '/', label: 'Home', icon: IconHome },
  { to: '/stage', label: 'Stage a system', icon: IconListCheck },
  { to: '/projects', label: 'Systems', icon: IconFolders },
  { to: '/devices', label: 'Devices', icon: IconRouter },
  { to: '/configurations', label: 'Files', icon: IconFileCode },
  { to: '/firmware', label: 'Firmware', icon: IconUpload },
  { to: '/provisioning', label: 'Console setup', icon: IconCpu },
  { to: '/deployments', label: 'Plans', icon: IconRocket },
] as const;

/** Tools experienced users need now and then; folded away by default. */
export const ADVANCED_NAV = [
  { to: '/topology', label: 'Topology', icon: IconBinaryTree2 },
  { to: '/audit', label: 'Audit log', icon: IconHistory },
] as const;

export const SETTINGS_NAV = { to: '/settings', label: 'Settings', icon: IconSettings } as const;

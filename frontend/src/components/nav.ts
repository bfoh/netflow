import {
  IconBinaryTree2, IconCpu, IconDashboard, IconFileCode, IconFolders,
  IconHistory, IconRocket, IconRouter, IconSettings, IconUpload,
} from '@tabler/icons-react';

/** Main navigation: one entry per application module. */
export const NAV = [
  { to: '/', label: 'Dashboard', icon: IconDashboard },
  { to: '/projects', label: 'Projects', icon: IconFolders },
  { to: '/devices', label: 'Network Elements', icon: IconRouter },
  { to: '/topology', label: 'Topology', icon: IconBinaryTree2 },
  { to: '/configurations', label: 'Configurations', icon: IconFileCode },
  { to: '/provisioning', label: 'Provisioning', icon: IconCpu },
  { to: '/firmware', label: 'Firmware', icon: IconUpload },
  { to: '/deployments', label: 'Deployments', icon: IconRocket },
  { to: '/audit', label: 'Logs & Audit', icon: IconHistory },
  { to: '/settings', label: 'Settings', icon: IconSettings },
] as const;

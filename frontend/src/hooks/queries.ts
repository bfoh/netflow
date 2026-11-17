import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';

import { api } from '../services/api';

export const keys = {
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  devices: ['devices'] as const,
  projectDevices: (pid: string) => ['devices', 'project', pid] as const,
  device: (id: string) => ['devices', id] as const,
  configs: (id: string) => ['configs', id] as const,
  config: (vid: string) => ['config', vid] as const,
  deployments: (pid: string) => ['deployments', pid] as const,
  deployment: (id: string) => ['deployment', id] as const,
  audit: (target?: string) => ['audit', target ?? 'all'] as const,
  drivers: ['drivers'] as const,
  models: ['device-models'] as const,
};

export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: api.projects });
export const useProject = (id: string) =>
  useQuery({ queryKey: keys.project(id), queryFn: () => api.project(id) });
export const useAllDevices = () => useQuery({ queryKey: keys.devices, queryFn: api.allDevices });
export const useProjectDevices = (pid: string) =>
  useQuery({ queryKey: keys.projectDevices(pid), queryFn: () => api.projectDevices(pid) });
export const useDevice = (id: string) =>
  useQuery({ queryKey: keys.device(id), queryFn: () => api.device(id) });
export const useConfigs = (id: string) =>
  useQuery({ queryKey: keys.configs(id), queryFn: () => api.configs(id) });
export const useConfig = (vid: string | null) =>
  useQuery({ queryKey: keys.config(vid ?? ''), queryFn: () => api.config(vid!), enabled: !!vid });
export const useAllDeployments = () =>
  useQuery({ queryKey: ['deployments', 'all'], queryFn: () => api.allDeployments(100) });
export const useConfigDiff = (from: string | null, to: string | null) =>
  useQuery({
    queryKey: ['config-diff', from, to],
    queryFn: () => api.configDiff(from!, to!),
    enabled: !!from && !!to && from !== to,
  });
export const useDeployments = (pid: string) =>
  useQuery({ queryKey: keys.deployments(pid), queryFn: () => api.deployments(pid), enabled: !!pid });
export const useDeployment = (id: string) =>
  useQuery({ queryKey: keys.deployment(id), queryFn: () => api.deployment(id) });
export const useAudit = (target?: string, limit = 200) =>
  useQuery({ queryKey: keys.audit(target), queryFn: () => api.audit({ target_id: target, limit }) });
export const useDrivers = () => useQuery({ queryKey: keys.drivers, queryFn: api.drivers });
export const useDeviceModels = () => useQuery({ queryKey: keys.models, queryFn: api.deviceModels });

/** Mutation that refreshes all cached data afterwards and reports errors as notifications. */
export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  successMessage?: string | ((r: TResult) => string),
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      void qc.invalidateQueries();
      if (successMessage) {
        const message = typeof successMessage === 'function' ? successMessage(result) : successMessage;
        notifications.show({ color: 'teal', message });
      }
    },
    onError: (err: Error) => notifications.show({ color: 'red', title: 'Action failed', message: err.message }),
  });
}

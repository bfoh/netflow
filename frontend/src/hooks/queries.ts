import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../services/api';
import { showError, showSuccess } from '../services/notify';

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
  useQuery({ queryKey: keys.project(id), queryFn: () => api.project(id), enabled: !!id });
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
/** States in which the server is working on a deployment right now. */
export const RUNNING_STATES = new Set(['validating', 'preflight', 'backing_up', 'deploying', 'verifying', 'recovering']);
/** Refreshes every two seconds while the deployment runs (`live` covers the moment before the first step is stored). */
export const useDeployment = (id: string, live = false) =>
  useQuery({
    queryKey: keys.deployment(id),
    queryFn: () => api.deployment(id),
    refetchInterval: (query) => (live || RUNNING_STATES.has(query.state.data?.state ?? '') ? 2000 : false),
  });
/** A staging plan; refreshes every two seconds while a step runs, and after Execute (`live`)
 * while a step is still waiting to run (the gap before step 1 starts and between steps). */
export const useStaging = (id: string, live = false) =>
  useQuery({
    queryKey: ['staging', id],
    queryFn: () => api.staging(id),
    refetchInterval: (query) => {
      const steps = query.state.data?.steps ?? [];
      const waiting = live && steps.some((s) => s.state === 'ready');
      return waiting || steps.some((s) => RUNNING_STATES.has(s.state)) ? 2000 : false;
    },
  });
export const useAudit = (target?: string, limit = 200) =>
  useQuery({ queryKey: keys.audit(target), queryFn: () => api.audit({ target_id: target, limit }) });
export const useDrivers = () => useQuery({ queryKey: keys.drivers, queryFn: api.drivers });
export const useFirmwareImages = () => useQuery({ queryKey: ['firmware-images'], queryFn: api.firmwareImages });
export const useTopology = (pid: string) =>
  useQuery({ queryKey: ['topology', pid], queryFn: () => api.topology(pid), enabled: !!pid });
export const useSerialPorts = () => useQuery({ queryKey: ['serial-ports'], queryFn: api.serialPorts });
export const usePolicy = () => useQuery({ queryKey: ['policy'], queryFn: api.policy });
export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: api.health });
export const useCredentialRefs = (pid: string) =>
  useQuery({ queryKey: ['credential-refs', pid], queryFn: () => api.credentialRefs(pid), enabled: !!pid });
export const useDeviceModels = () => useQuery({ queryKey: keys.models, queryFn: api.deviceModels });

/** Mutation that refreshes all cached data afterwards and reports errors as notifications. */
export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  successMessage?: string | ((r: TResult) => string),
  options: { errorInDialog?: boolean } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      void qc.invalidateQueries();
      if (successMessage) {
        showSuccess(typeof successMessage === 'function' ? successMessage(result) : successMessage);
      }
    },
    // A dialog shows its own error (DialogError); everything else gets a message that stays.
    onError: (err: Error) => { if (!options.errorInDialog) showError(err.message); },
  });
}

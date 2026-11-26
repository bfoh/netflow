import type { Crumb } from '../../components/Page';
import { useProject } from '../../hooks/queries';
import { paths, type SystemTab } from '../../paths';

/** Where a detail page sits (D-120): Systems › <its system>. The system's name is read once;
 *  until then the crumb says "System". */
export function useSystemCrumbs(projectId: string | undefined, tab?: SystemTab): Crumb[] {
  const project = useProject(projectId ?? '');
  const crumbs: Crumb[] = [{ label: 'Systems', to: paths.systems }];
  if (projectId) crumbs.push({ label: project.data?.name ?? 'System', to: paths.system(projectId, tab) });
  return crumbs;
}

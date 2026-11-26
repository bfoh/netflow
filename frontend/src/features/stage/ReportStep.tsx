import { Button, Card, Group, Stack, Table, Text, Title } from '@mantine/core';
import { IconDownload, IconPrinter } from '@tabler/icons-react';
import { useQueries } from '@tanstack/react-query';
import { useState } from 'react';

import { StateBadge } from '../../components/Badges';
import { api } from '../../services/api';
import { downloadText, fmtDate } from '../../services/format';
import { stepName } from '../../services/labels';
import type { Device, Guided, Project, StagingIndex, StagingPlan } from '../../types/api';
import { type Role } from './roles';
import { EmptyState } from '../../components/EmptyState';
import { BenchLogButton } from '../systems/BenchLogButton';
import { Notice } from '../../components/Notice';
import { FinishChecklist } from './FinishChecklist';
import { loadTicks, saveTicks, type Ticks } from './finishTicks';

const minutes = (a: string, b: string) => {
  const ms = new Date(b).getTime() - new Date(a).getTime();
  return Number.isFinite(ms) && ms >= 0 ? `${Math.round(ms / 60000)} min` : '—';
};


/** Step 5: what was done to each device, to print or keep. */
export function ReportStep({ project, roles, stagings }: {
  project: Project; roles: { role: Role; device: Device }[]; stagings: StagingIndex[];
}) {
  const latest = roles.map(({ device }) => stagings.find((x) => x.device_id === device.id));
  const plans = useQueries({
    queries: latest.map((l) => ({ queryKey: ['staging', l?.staging_id ?? ''], queryFn: () => api.staging(l!.staging_id), enabled: !!l })),
  });
  // Devices staged by hand in their portal (the Flexi BBU, D-117): their recorded steps.
  const guided = useQueries({
    queries: roles.map(({ role, device }) => ({ queryKey: ['guided', device.id], queryFn: () => api.guided(device.id), enabled: !!role.guided })),
  });
  const rows = roles.map(({ role, device }, i) => ({ role, device, plan: plans[i]?.data as StagingPlan | undefined,
    guided: role.guided ? guided[i]?.data as Guided | undefined : undefined }));
  const [madeAt] = useState(() => new Date().toISOString());
  const [ticks, setTicks] = useState<Ticks>(() => loadTicks(project.id));
  const onTicks = (t: Ticks) => { setTicks(t); saveTicks(project.id, t); };
  const saved = () => onTicks({ ...ticks, report: true });
  const html = () => {
    saved();
    const el = document.getElementById('staging-report');
    const body = el ? el.outerHTML : '';
    downloadText(`staging-report-${project.name.replace(/[^\w.-]+/g, '_')}.html`,
      `<!doctype html><html><head><meta charset="utf-8"><title>Staging report · ${project.name}</title>`
      + '<style>body{font-family:system-ui,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}'
      + 'td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;font-size:13px}</style></head><body>'
      + body + '</body></html>');
  };
  return (
    <Stack>
      <Group justify="flex-end" className="no-print">
        <Button variant="default" leftSection={<IconPrinter size={16} />} onClick={() => { saved(); window.print(); }}>Print</Button>
        <Button variant="default" leftSection={<IconDownload size={16} />} onClick={html}>Save as HTML</Button>
        <BenchLogButton projectId={project.id} />
      </Group>
      {roles.length === 0 && <EmptyState>No devices yet: add them in step 1.</EmptyState>}
      {roles.length > 0 && (() => {
        // The end of the run, said plainly (bench 2026-11-25: "how does it complete?").
        const open = rows.filter(({ role, plan, guided: g }) => (role.guided ? !g || g.steps.some((s) => !s.done_by)
          : !plan || plan.steps.length === 0 || plan.steps.some((s) => s.state !== 'succeeded')));
        return <Stack className="no-print">
          {open.length > 0 && !project.staged_at && (
            <Notice kind="status" title={`${rows.length - open.length} of ${rows.length} devices are staged`}>
              Still to do in step 4 (Run): {open.map(({ device }) => device.name).join(', ')}.
            </Notice>
          )}
          <FinishChecklist project={project} rows={roles} allStaged={open.length === 0} ticks={ticks} onTicks={onTicks}
            licenseLoaded={rows.some(({ role, plan }) => role.key === 'firewall'
              && !!plan?.steps.some((s) => s.kind === 'license' && s.state === 'succeeded'))} />
        </Stack>;
      })()}
      <div id="staging-report">
        <Title order={2} size="h4" mb="xs">Staging report · {project.name}</Title>
        <Text size="sm" c="dimmed" mb="md">Made {fmtDate(madeAt)}. One section per device: its latest staging plan.
          {project.staged_at ? ` Staging finished ${fmtDate(project.staged_at)}${project.staged_by ? ` by ${project.staged_by}` : ''}.` : ' Staging not finished yet.'}</Text>
        <Stack>
          {rows.map(({ role, device, plan, guided: g }) => {
            const facts = (device.observed_facts ?? {}) as Record<string, unknown>;
            const steps = plan?.steps ?? [];
            const warnings = steps.flatMap((s) => s.events).filter((e) => e.status === 'warning');
            return (
              <Card withBorder key={role.key}>
                <Group justify="space-between" mb="xs" wrap="wrap">
                  <Title order={3} size="h5">{device.name} · {role.title}</Title>
                  <Text size="sm" c="dimmed">{device.manufacturer} {device.model} · {device.management_address}</Text>
                </Group>
                <Text size="sm" mb="xs">Firmware now: <b>{String(facts.os_version ?? '—')}</b> · serial / MAC: <b>{String(facts.serial_number ?? '—')}</b>
                  {facts.hostname ? <> · hostname: <b>{String(facts.hostname)}</b></> : null}
                  {device.facts_retrieved_at ? ` (read ${fmtDate(device.facts_retrieved_at)})` : ' (not read yet: use Retrieve information on the device page)'}</Text>
                {role.guided ? (
                  <Table.ScrollContainer minWidth={520}>
                    <Table verticalSpacing={4} aria-label={`Steps done in the portal of ${device.name}`}>
                      <Table.Thead><Table.Tr><Table.Th>Step (by hand, in its portal)</Table.Th><Table.Th>Done by</Table.Th><Table.Th>When</Table.Th><Table.Th>Noted</Table.Th></Table.Tr></Table.Thead>
                      <Table.Tbody>
                        {(g?.steps ?? []).map((s, i) => (
                          <Table.Tr key={s.key}>
                            <Table.Td>{i + 1}. {s.title}{s.file_name && <Text size="xs" c="dimmed">{s.file_name} · SHA-256 {s.file_sha256}</Text>}</Table.Td>
                            <Table.Td>{s.done_by ?? '—'}</Table.Td>
                            <Table.Td>{s.done_at ? fmtDate(s.done_at) : 'not yet'}</Table.Td>
                            <Table.Td>{s.note || '—'}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                ) : steps.length === 0 ? <Text size="sm" c="dimmed">No staging plan yet.</Text> : (
                  <Table.ScrollContainer minWidth={520}>
                    <Table verticalSpacing={4}>
                      <Table.Thead><Table.Tr><Table.Th>Step</Table.Th><Table.Th>Result</Table.Th><Table.Th>Started</Table.Th><Table.Th>Took</Table.Th><Table.Th>Approved by</Table.Th></Table.Tr></Table.Thead>
                      <Table.Tbody>
                        {steps.map((s) => {
                          const run = s.events.filter((e) => !['validate', 'preview', 'approve', 'lifecycle'].includes(e.stage));
                          return (
                            <Table.Tr key={s.id}>
                              <Table.Td>{s.staging_step}. {stepName(s.kind, s.apply_mode)}</Table.Td>
                              <Table.Td><StateBadge state={s.state} /></Table.Td>
                              <Table.Td>{run[0] ? fmtDate(run[0].timestamp) : '—'}</Table.Td>
                              <Table.Td>{run.length > 1 ? minutes(run[0].timestamp, run[run.length - 1].timestamp) : '—'}</Table.Td>
                              <Table.Td>{s.approved_by ?? '—'}</Table.Td>
                            </Table.Tr>
                          );
                        })}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
                {warnings.length > 0 && (
                  <Stack gap={2} mt="xs">
                    <Text size="sm" fw={600}>Warnings ({warnings.length})</Text>
                    {warnings.slice(0, 6).map((w) => <Text key={`${w.seq}-${w.timestamp}`} size="xs" c="orange">{w.message}</Text>)}
                  </Stack>
                )}
              </Card>
            );
          })}
        </Stack>
      </div>
    </Stack>
  );
}

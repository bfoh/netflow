import { Anchor, Badge, Button, Card, Checkbox, Group, Stack, Text, Title } from '@mantine/core';
import { IconCircleCheck, IconCircleDashed } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { DialogError } from '../../components/ConfirmDialog';
import { Notice } from '../../components/Notice';
import { useAction, usePolicy } from '../../hooks/queries';
import { api } from '../../services/api';
import { fmtDate } from '../../services/format';
import type { Device, Project } from '../../types/api';
import { DownloadBackupsButton } from '../systems/SystemPackage';
import type { Ticks } from './finishTicks';
import { portOff, type Role } from './roles';

function Item({ done, title, children, manual, onTick }: {
  done: boolean; title: string; children?: ReactNode; manual?: boolean; onTick?: (v: boolean) => void;
}) {
  return (
    <Group align="flex-start" wrap="nowrap" gap="sm">
      {manual
        ? <Checkbox mt={2} checked={done} onChange={(e) => onTick?.(e.currentTarget.checked)} aria-label={title} />
        : done ? <IconCircleCheck size={20} color="var(--mantine-color-teal-text)" aria-label="done" />
          : <IconCircleDashed size={20} color="var(--mantine-color-dimmed)" aria-label="to do" />}
      <div style={{ flex: 1 }}>
        <Text size="sm" fw={600}>{title}</Text>
        {children && <Text size="xs" c="dimmed" component="div">{children}</Text>}
      </div>
    </Group>
  );
}

/** The end of staging a system (D-108): a checklist, then Finish staging, recorded by UNDM. */
export function FinishChecklist({ project, rows, allStaged, licenseLoaded, ticks, onTicks }: {
  project: Project; rows: { role: Role; device: Device }[]; allStaged: boolean; licenseLoaded: boolean;
  ticks: Ticks; onTicks: (t: Ticks) => void;
}) {
  const policy = usePolicy();
  const off = rows.filter(({ device }) => portOff(device));
  const hasFirewall = rows.some(({ role }) => role.key === 'firewall');
  const safetyOff = !!policy.data && !policy.data.enable_real_device_writes && !policy.data.enable_real_device_firmware;
  const lockedOn = !!policy.data && policy.data.locked.some((k) => k === 'enable_real_device_writes' || k === 'enable_real_device_firmware');
  // Not a Test: switched on again it answers at the address the other switch now has (D-107).
  const clear = useAction((id: string) => api.clearPortOff(id), 'Noted: its port is on again');
  const safety = useAction(() => api.changePolicy({ enable_real_device_writes: false, enable_real_device_firmware: false }),
    'Safety switches turned off');
  const finish = useAction(() => api.finishStaging(project.id, rows.map(({ device }) => device.id)),
    'Staging of this system is finished', { errorInDialog: true });
  const reopen = useAction(() => api.reopenStaging(project.id), 'Staging reopened');
  const tick = (part: Ticks) => onTicks({ ...ticks, ...part });
  const ready = allStaged && off.length === 0 && (!hasFirewall || licenseLoaded || !!ticks.license) && !!ticks.report
    && !!ticks.backups && safetyOff && !!ticks.powered;

  if (project.staged_at) {
    return (
      <Notice kind="success" title={`Staging finished · ${fmtDate(project.staged_at)}${project.staged_by ? ` by ${project.staged_by}` : ''}`}
        action={<Button size="xs" variant="default" loading={reopen.isPending} onClick={() => reopen.mutate(undefined)}>Reopen</Button>}>
        This system is done. A new staging plan on one of its devices reopens it by itself.
      </Notice>
    );
  }
  return (
    <Card withBorder>
      <Group justify="space-between" mb="sm">
        <Title order={2} size="h5">Finish staging</Title>
        <Badge color={ready ? 'teal' : 'gray'} variant="light" tt="none">{ready ? 'ready to finish' : 'to do'}</Badge>
      </Group>
      <Stack gap="sm">
        <Item done={allStaged} title="Every device is staged">
          {allStaged ? 'The latest staging plan of each device succeeded.' : 'Still to do in step 4 (Run).'}
        </Item>
        <Item done={off.length === 0} title="Every switch answers at its own address">
          {off.length === 0 ? 'No device is left with its port off.' : off.map(({ device }) => {
            const now = rows.find(({ device: d }) => d.id !== device.id && d.management_address === device.management_address);
            return (
              <Group key={device.id} gap="xs" mt={2}>
                <span>Switch <b>{device.name}</b> off and on, unplugged from the bench switch
                  {now ? <> ({now.device.name} now uses {device.management_address})</> : null}: port {portOff(device)} is on again
                  after that. Then press</span>
                <Button size="compact-xs" variant="light" loading={clear.isPending && clear.variables === device.id}
                  onClick={() => clear.mutate(device.id)}>It was switched off and on</Button>
              </Group>
            );
          })}
        </Item>
        {hasFirewall && (
          licenseLoaded ? (
            <Item done title="FortiGate license loaded">Loaded by the last step of its staging plan.</Item>
          ) : (
            <Item manual done={!!ticks.license} onTick={(v) => tick({ license: v })} title="FortiGate license: loaded, or later">
              Not loaded by the staging plan. When the file arrives, load it from the FortiGate's menu (⋯ → Load license…), also
              after staging is finished. Tick this if it is loaded, not needed, or will be loaded later.
            </Item>
          )
        )}
        <Item manual done={!!ticks.report} onTick={(v) => tick({ report: v })} title="Report saved">
          Print or Save as HTML (above) ticks this.
        </Item>
        <Item manual done={!!ticks.backups} onTick={(v) => tick({ backups: v })} title="Backups downloaded">
          <Group gap="xs" mt={2}><span>One zip for the system:</span>
            <DownloadBackupsButton projectId={project.id} onDownloaded={() => tick({ backups: true })} /></Group>
        </Item>
        <Item done={safetyOff} title="Safety switches off">
          {safetyOff ? 'Real-device and firmware changes are off.' : lockedOn
            ? <>Fixed on in backend\.env (<code>UNDM_ENABLE_REAL_DEVICE_WRITES</code>, <code>UNDM_ENABLE_REAL_DEVICE_FIRMWARE</code>).
              Delete those lines once and restart the backend: Settings → Safety then controls them.</>
            : <Group gap="xs" mt={2}><span>Real-device or firmware changes are still on.</span>
              <Button size="compact-xs" variant="light" loading={safety.isPending} onClick={() => safety.mutate(undefined)}>Turn them off</Button>
              <Anchor component={Link} to="/settings?tab=safety" size="xs">Settings → Safety</Anchor></Group>}
        </Item>
        <Item manual done={!!ticks.powered} onTick={(v) => tick({ powered: v })} title="Devices powered off and labelled" />
        <DialogError error={finish.error} />
        <Group justify="flex-end">
          <Button disabled={!ready} loading={finish.isPending} onClick={() => finish.mutate(undefined)}>Finish staging</Button>
        </Group>
      </Stack>
    </Card>
  );
}

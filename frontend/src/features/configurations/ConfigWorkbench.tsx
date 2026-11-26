import { ActionIcon, Badge, Button, Card, Code, CopyButton, FileButton, Group, List, Select, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import { IconCopy, IconDownload, IconFileImport, IconRocket, IconWand } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { DiffView } from '../../components/DiffView';
import { Hint } from '../../components/Hint';
import { Notice } from '../../components/Notice';
import { QueryState } from '../../components/Page';
import { downloadText, fmtDate } from '../../services/format';
import { useAction, useConfig, useConfigDiff, useConfigs } from '../../hooks/queries';
import { api } from '../../services/api';
import type { ConfigInspection, ConfigVersion, Device, Issue } from '../../types/api';
import { humanize } from '../../services/labels';
import { paths } from '../../paths';

const label = (v: ConfigVersion) =>
  `${v.kind}${v.kind === 'imported' && v.reference ? ` (${v.reference})` : ''} · ${fmtDate(v.created_at)} · ${v.sha256.slice(0, 8)}`;

const MAX_IMPORT_BYTES = 2 * 1024 * 1024;

/** What the device's driver worked out about an imported file, offline. */
function FileReport({ report }: { report: ConfigInspection }) {
  const blocked = report.problems.length > 0 || !!report.blocked_reason;
  return (
    <Notice kind={blocked ? 'error' : 'settled'} compact mb="xs" title={report.summary}
      details={report.notes.length > 0 ? <List size="xs" spacing={2}>{report.notes.map((n) => <List.Item key={n}>{n}</List.Item>)}</List> : undefined}>
      {report.apply_mode && (
        <Text size="xs" mb={4}>
          {report.apply_mode === 'replace'
            ? 'Loaded as a whole (complete file); never sent line by line.'
            : 'A list of changes (additions): it changes what it names and leaves the rest alone.'}
        </Text>
      )}
      {report.blocked_reason && <Text size="xs" fw={600} mb={4}>Cannot be applied yet: {report.blocked_reason}</Text>}
      {report.problems.length > 0 && (
        <>
          <Text size="xs" fw={600}>Problems found in the file:</Text>
          <List size="xs" mb={4}>{report.problems.map((p) => <List.Item key={p}>{p}</List.Item>)}</List>
        </>
      )}
    </Notice>
  );
}

/** Generate, preview, validate and compare configuration versions for one device. */
export function ConfigWorkbench({ device, initialVersion = null }: { device: Device; initialVersion?: string | null }) {
  const versions = useConfigs(device.id);
  const [issues, setIssues] = useState<Issue[] | null>(null);
  const [selected, setSelected] = useState<string | null>(initialVersion);
  const navigate = useNavigate();
  const [compareTo, setCompareTo] = useState<string | null>(null);
  const list = versions.data ?? [];
  const current = selected ?? list[0]?.id ?? null;
  const shown = useConfig(current);
  const diff = useConfigDiff(compareTo, current);

  const generate = useAction(() => api.generateConfig(device.id), (r) => (r.ok ? 'Configuration generated' : 'Intent has errors; nothing generated'));
  const run = () => generate.mutate(undefined, { onSuccess: (r) => { setIssues(r.issues); if (r.version) setSelected(r.version.id); } });
  const importFile = useAction(async (file: File) => {
    if (file.size > MAX_IMPORT_BYTES) throw new Error('File is larger than 2 MiB');
    return api.importConfig(device.id, file.name, await file.text());
  }, (v) => `Imported ${v.reference}`);
  const onFile = (file: File | null) => {
    if (file) importFile.mutate(file, { onSuccess: (v) => { setIssues(null); setSelected(v.id); } });
  };

  return (
    <Stack>
      <Group>
        <Button leftSection={<IconWand size={16} />} onClick={run} loading={generate.isPending} disabled={!device.intent}>Generate configuration</Button>
        <FileButton onChange={onFile} accept=".cfg,.conf,.txt,.config,text/plain">
          {(props) => <Button {...props} variant="default" leftSection={<IconFileImport size={16} />} loading={importFile.isPending}>Import configuration file</Button>}
        </FileButton>
        {!device.intent && <Text size="sm" c="dimmed">No intent defined: import a configuration file, or define the intent to generate one.</Text>}
      </Group>
      {issues && issues.length > 0 && (
        <Notice kind={issues.some((i) => i.severity === 'error') ? 'error' : 'caution'} title="Validation results">
          <List size="sm">{issues.map((i, n) => <List.Item key={n}><b>{i.severity}</b> {i.path && <code>{i.path}</code>} — {i.message}</List.Item>)}</List>
        </Notice>
      )}
      {issues && issues.length === 0 && <Notice kind="success" title="Validation passed">No errors or warnings.</Notice>}
      <QueryState isLoading={versions.isLoading} error={versions.error} />
      {list.length === 0 ? <Text c="dimmed" size="sm">No configuration versions yet.</Text> : (
        <SimpleGrid cols={{ base: 1, lg: 2 }}>
          <Card withBorder>
            <Group justify="space-between" mb="xs">
              <Title order={2} size="h5">Preview</Title>
              <Select size="xs" w={300} aria-label="Configuration version" data={list.map((v) => ({ value: v.id, label: label(v) }))} value={current} onChange={setSelected} />
            </Group>
            {shown.data && (
              <>
                <Group gap="xs" mb="xs">
                  <Badge variant="light">{shown.data.kind}</Badge>
                  {shown.data.platform && <Badge variant="light" color="gray">{shown.data.template_version ? `${shown.data.platform} template v${shown.data.template_version}` : shown.data.platform}</Badge>}
                  {shown.data.verification && <Badge variant="light" color="yellow">{humanize(shown.data.verification)}</Badge>}
                </Group>
                {shown.data.kind === 'imported' && (
                  <Hint mb="xs">Imported from <b>{shown.data.reference}</b>: sent exactly as written, not checked against the
                    device's settings. Compare it with the latest backup before making a plan.</Hint>
                )}
                {shown.data.inspection && <FileReport report={shown.data.inspection} />}
                {(shown.data.kind === 'generated' || shown.data.kind === 'imported') && (() => {
                  const report = shown.data.inspection;
                  const blocked = !!report && (report.problems.length > 0 || !!report.blocked_reason);
                  return (
                    <Group gap="xs" mb="xs" wrap="nowrap" align="flex-start">
                      <Button size="xs" leftSection={<IconRocket size={14} />} disabled={blocked}
                        onClick={() => void navigate(paths.planNew({ system: device.project_id, devices: device.id, version: shown.data!.id }))}>
                        Make a plan with this version…
                      </Button>
                      <Text size="xs" c="dimmed">{blocked
                        ? 'This file cannot be applied as it is (see above).'
                        : 'Opens a new plan with this version chosen. Nothing is sent to the device until the plan is checked, approved and run.'}</Text>
                    </Group>
                  );
                })()}
                {shown.data.verification === 'docs_reviewed_not_lab_verified' && (
                  <Hint mb="xs">Generated from a template that follows public vendor documentation; not yet verified on lab equipment.</Hint>
                )}
                <Code block mah={420} style={{ overflow: 'auto', fontSize: 12 }}>{shown.data.text}</Code>
                <Group gap="xs" mt="xs">
                  <CopyButton value={shown.data.text ?? ''}>
                    {({ copied, copy }) => <Button size="xs" variant="default" leftSection={<IconCopy size={14} />} onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>}
                  </CopyButton>
                  <Button size="xs" variant="default" leftSection={<IconDownload size={14} />}
                    onClick={() => downloadText(`${device.name}-${shown.data!.kind}-${shown.data!.sha256.slice(0, 8)}.txt`, shown.data!.text ?? '')}>Download</Button>
                </Group>
              </>
            )}
          </Card>
          <Card withBorder>
            <Group justify="space-between" mb="xs">
              <Title order={2} size="h5">Compare</Title>
              <Select size="xs" w={300} clearable placeholder="Compare with…" aria-label="Compare with version"
                data={list.filter((v) => v.id !== current).map((v) => ({ value: v.id, label: label(v) }))} value={compareTo} onChange={setCompareTo} />
            </Group>
            {compareTo && diff.data ? <><Text size="sm" mb="xs">+{diff.data.added} / −{diff.data.removed} lines</Text><DiffView diff={diff.data.unified} /></>
              : <Text size="sm" c="dimmed">Select an older version or a backup to see what changes.</Text>}
          </Card>
        </SimpleGrid>
      )}
      {list.length > 0 && (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={560}>
            <Table verticalSpacing={6} horizontalSpacing="md">
              <Table.Thead><Table.Tr><Table.Th>Created</Table.Th><Table.Th>Kind</Table.Th><Table.Th>By</Table.Th><Table.Th>From</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {list.map((v) => (
                  <Table.Tr key={v.id} onClick={() => setSelected(v.id)} tabIndex={0} aria-current={v.id === current ? 'true' : undefined}
                    title={`SHA-256 ${v.sha256}`}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(v.id); } }} style={{ cursor: 'pointer' }} bg={v.id === current ? 'var(--mantine-primary-color-light)' : undefined}>
                    <Table.Td>{fmtDate(v.created_at)}</Table.Td><Table.Td>{humanize(v.kind)}</Table.Td>
                    <Table.Td>{v.created_by}</Table.Td><Table.Td>{v.reference || '—'}</Table.Td>
                    <Table.Td w={40}>
                      <ActionIcon variant="subtle" aria-label={`Download ${humanize(v.kind)} of ${fmtDate(v.created_at)}`}
                        onClick={(e) => { e.stopPropagation(); void api.config(v.id).then((full) =>
                          downloadText(`${device.name}-${v.kind}-${v.sha256.slice(0, 8)}.txt`, full.text ?? '')); }}>
                        <IconDownload size={16} /></ActionIcon>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
    </Stack>
  );
}

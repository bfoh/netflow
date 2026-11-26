import { Anchor, Button, Card, Collapse, Group, Stack, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { IconCircleCheck, IconCircleDashed } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { Tag } from '../../components/Badges';
import { useFirmwareImages, useLoginDefaults, useSharedCertificate, useSharedLogins, useTemplates } from '../../hooks/queries';
import { paths } from '../../paths';
import { api, getActor } from '../../services/api';
import { ROLES } from '../stage/roles';
import { TEMPLATE_ROLES } from '../stage/zone';

const count = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

interface Item { key: string; done: boolean; title: string; state: string; to: string; action: string }

function Row({ item }: { item: Item }) {
  return (
    <Group justify="space-between" wrap="nowrap" align="flex-start">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        {item.done ? <IconCircleCheck size={20} color="var(--mantine-color-teal-text)" aria-label="done" />
          : <IconCircleDashed size={20} color="var(--mantine-color-dimmed)" aria-label="to do" />}
        <div>
          <Text size="sm" fw={600}>{item.title}</Text>
          <Text size="xs" c="dimmed">{item.state}</Text>
        </div>
      </Group>
      {!item.done && <Button size="xs" variant="default" component={Link} to={item.to}>{item.action}</Button>}
    </Group>
  );
}

/**
 * What is set once before the first system (D-123), from what UNDM already has; each item has
 * a button to the exact place. It folds to one line when everything is done.
 */
export function SetupChecklist() {
  const logins = useSharedLogins();
  const defaults = useLoginDefaults();
  const templates = useTemplates();
  const pci = useQuery({ queryKey: ['pci-mapping'], queryFn: api.pciMapping });
  const cert = useSharedCertificate();
  const images = useFirmwareImages();
  const [open, { toggle }] = useDisclosure(false);
  if ([logins, defaults, templates, pci, cert, images].some((q) => q.isLoading)) return null;

  const shared = logins.data ?? [];
  const noPassword = shared.filter((r) => r.has_secret === false).length;
  const d = defaults.data;
  const defaultCount = d ? [d.firewall?.login, d.blackbox?.login, d.aruba?.login, d.modem?.login].filter(Boolean).length : 0;
  const have = new Set((templates.data ?? []).map((t) => t.role));
  const tplCount = TEMPLATE_ROLES.filter((t) => have.has(t.role)).length;
  const fwModels = [...new Set(ROLES.filter((r) => r.steps.includes('firmware')).map((r) => r.model))];
  const approved = (images.data ?? []).filter((i) => i.status === 'approved');
  const missingImage = fwModels.filter((m) => !approved.some((i) => i.compatible_models.length === 0 || i.compatible_models.includes(m)));
  const actor = getActor();
  const items: Item[] = [
    { key: 'name', done: !!actor && actor !== 'local-user', title: 'Your name', to: paths.settings('identity'), action: 'Set your name',
      state: actor && actor !== 'local-user' ? `Acting as ${actor}` : 'The audit log and the second approver tell people apart by it.' },
    { key: 'logins', done: shared.length > 0 && noPassword === 0, title: 'Logins for all systems', to: paths.settings('logins'), action: 'Add logins',
      state: shared.length === 0 ? 'None yet.' : noPassword ? `${count(shared.length, 'login')}; ${noPassword} without a stored password.`
        : `${count(shared.length, 'login')}, passwords stored.` },
    { key: 'defaults', done: defaultCount === 4, title: 'Default login per device', to: paths.settings('logins'), action: 'Choose them',
      state: `${defaultCount} of 4 (FortiGate, Black Box, Aruba 2930F, modem).` },
    { key: 'templates', done: tplCount === TEMPLATE_ROLES.length, title: 'Templates of the team files', to: paths.settings('templates'), action: 'Import templates',
      state: `${tplCount} of ${TEMPLATE_ROLES.length} imported.` },
    { key: 'pci', done: !!pci.data, title: 'PCI table (Flexi BBU cells)', to: paths.settings('templates'), action: 'Import it',
      state: pci.data ? `${pci.data.systems} systems.` : 'Not imported.' },
    { key: 'certificate', done: !!cert.data?.subject, title: 'HTTPS certificate answers (2930F)', to: paths.settings('certificate'), action: 'Set them',
      state: cert.data?.subject ? `Common name ${cert.data.subject.common_name}.` : 'Not set.' },
    { key: 'images', done: missingImage.length === 0, title: 'Approved firmware images', to: paths.firmware(missingImage[0]), action: 'Upload',
      state: missingImage.length === 0 ? 'One for every model that gets firmware.' : `Still needed for ${missingImage.join(', ')}.` },
  ];
  const left = items.filter((i) => !i.done).length;
  const body: ReactNode = <Stack gap="sm" mt="sm">{items.map((i) => <Row key={i.key} item={i} />)}</Stack>;
  return (
    <Card mb="lg" aria-labelledby="setup-title">
      <Group justify="space-between" wrap="wrap">
        <Group gap="sm">
          <Title order={2} id="setup-title">Set up once</Title>
          <Tag tone={left === 0 ? 'success' : 'neutral'}>{left === 0 ? 'done' : `${items.length - left} of ${items.length} done`}</Tag>
        </Group>
        {left === 0 && <Anchor component="button" type="button" size="sm" onClick={toggle} aria-expanded={open}>{open ? 'Hide' : 'Show'}</Anchor>}
      </Group>
      {left === 0 ? <Collapse expanded={open}>{body}</Collapse> : (
        <>
          <Text size="sm" c="dimmed" mt={4}>Every system uses these. Set them once; Stage a system then fills them in by itself.</Text>
          {body}
        </>
      )}
    </Card>
  );
}

import { Anchor, Select, type MantineSize } from '@mantine/core';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { useCredentialRefs } from '../../hooks/queries';
import { paths } from '../../paths';
import type { CredentialRef } from '../../types/api';

/** How a login is named in every picker: its name, and a word when it cannot be used as is. */
function optionLabel(r: CredentialRef): string {
  if (r.has_secret === false) return `${r.name} (no password stored yet)`;
  return r.name;
}

/**
 * The one login picker (D-121): the same words everywhere, the logins for all systems first,
 * then the system's own, and the same way to add one when there are none.
 */
export function LoginSelect({ projectId, value, onChange, label = 'Its login', description, placeholder,
  size = 'sm', maw = 380, clearable = true, disabled, error, required }: {
  projectId: string;
  value: string | null;
  onChange: (id: string | null) => void;
  label?: ReactNode;
  description?: ReactNode;
  placeholder?: string;
  size?: MantineSize;
  maw?: number;
  clearable?: boolean;
  disabled?: boolean;
  error?: ReactNode;
  required?: boolean;
}) {
  const refs = useCredentialRefs(projectId);
  const all = refs.data ?? [];
  const shared = all.filter((r) => r.shared).map((r) => ({ value: r.id, label: optionLabel(r) }));
  const own = all.filter((r) => !r.shared).map((r) => ({ value: r.id, label: optionLabel(r) }));
  const data = [
    ...(shared.length ? [{ group: 'For all systems', items: shared }] : []),
    ...(own.length ? [{ group: 'This system only', items: own }] : []),
  ];
  const none = !refs.isLoading && all.length === 0;
  return (
    <Select size={size} label={label} w="100%" maw={maw} clearable={clearable} disabled={disabled} required={required}
      data={data} value={value} onChange={onChange} error={error} searchable={all.length > 8}
      placeholder={none ? 'No logins yet' : placeholder ?? 'Choose a login'}
      description={none
        ? <>No logins yet: add them once in <Anchor component={Link} to={paths.settings('logins')} size="xs">Settings → Logins</Anchor>.</>
        : description} />
  );
}

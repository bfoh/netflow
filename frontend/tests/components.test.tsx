import { Button, Modal } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppProviders } from '../src/AppProviders';
import { makeQueryClient } from '../src/services/queryClient';
import { Notice } from '../src/components/Notice';
import { PageHeader } from '../src/components/Page';
import { ReasonButton } from '../src/components/ReasonButton';
import { useConfirm } from '../src/hooks/useConfirm';

const wrap = (ui: React.ReactNode) => render(<AppProviders queryClient={makeQueryClient(false)}>{ui}</AppProviders>);

describe('accessible building blocks (D-119)', () => {
  it('a notice is announced as its kind requires: errors interrupt, status is polite, cautions are read in place', () => {
    wrap(<>
      <Notice kind="error">broken</Notice>
      <Notice kind="status">running</Notice>
      <Notice kind="caution">careful</Notice>
      <Notice kind="status" live={false}>ticking</Notice>
    </>);
    expect(screen.getByText('broken').closest('[role]')).toHaveAttribute('role', 'alert');
    expect(screen.getByText('running').closest('[role]')).toHaveAttribute('role', 'status');
    expect(screen.getByText('careful').closest('[role]')).toHaveAttribute('role', 'note');
    expect(screen.getByText('ticking').closest('[role]')).toHaveAttribute('role', 'note');
  });

  it('the page title names the browser tab', () => {
    wrap(<PageHeader title="Systems" />);
    expect(document.title).toBe('Systems · UNDM');
    expect(screen.getByRole('heading', { level: 1, name: 'Systems' })).toBeInTheDocument();
  });

  it('a dialog close button has a name', () => {
    wrap(<Modal opened onClose={() => undefined} title="Example">body</Modal>);
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  it('a confirmation starts on Cancel and gives focus back to the button that opened it', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const onConfirm = vi.fn();
    function Demo() {
      const [ask, dialog] = useConfirm();
      return <>{dialog}<Button onClick={() => ask({ title: 'Delete it?', message: 'Gone for good.', confirmLabel: 'Delete', onConfirm })}>Delete…</Button></>;
    }
    wrap(<Demo />);
    const opener = screen.getByRole('button', { name: 'Delete…' });
    await userEvent.click(opener);
    const cancel = await screen.findByRole('button', { name: 'Cancel' });
    await vi.waitFor(() => expect(cancel).toHaveFocus());
    await userEvent.click(cancel);
    await vi.waitFor(() => expect(opener).toHaveFocus());
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('a disabled button says why, linked for screen readers', () => {
    wrap(<ReasonButton disabled reason="Choose a file first">Make the plan</ReasonButton>);
    const button = screen.getByRole('button', { name: 'Make the plan' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription('Choose a file first');
  });
});

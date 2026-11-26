import { expect, test } from '@playwright/test';

/** Logins and defaults for all systems (D-105): a login made once shows in every system, and
 *  the wizard adds a real device with its default login. Fictional names; nothing contacted. */
test('a login for all systems and its default reach a new system', async ({ page, request }) => {
  const id = String(Date.now()).slice(-6);
  const login = await (await request.post('/api/credential-refs', { data: { name: `approved ${id}` } })).json();
  try {
    await page.goto('/settings');
    await expect(page.getByRole('tab', { name: 'Logins' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('cell', { name: `approved ${id}`, exact: true })).toBeVisible();
    const label = page.getByText('Its login', { exact: true }).last();  // Aruba 2930F
    await page.locator(`#${await label.getAttribute('for')}`).click();
    await page.getByRole('option', { name: `approved ${id}` }).click();
    await page.getByRole('button', { name: 'Save default logins' }).click();
    await expect(page.getByText('Default logins saved')).toBeVisible();

    const p = await (await request.post('/api/projects', { data: { name: `Shared ${id}`, purpose: 'Staging' } })).json();
    await page.goto(`/systems/${p.id}`);
    await page.getByRole('tab', { name: 'Logins' }).click();
    await expect(page.getByRole('row', { name: new RegExp(`approved ${id}.*all systems`) })).toBeVisible();

    await page.goto(`/stage/${p.id}?step=0`);
    await page.getByRole('button', { name: 'Add it (192.168.1.1)' }).click();
    await expect(page.getByText('Aruba 2930F (OOBM port 2) added')).toBeVisible();
    const devices = await (await request.get(`/api/projects/${p.id}/devices`)).json();
    expect(devices[0].credential_ref_id).toBe(login.id);
  } finally {
    await request.put('/api/settings/defaults', { data: {} });
    await request.delete(`/api/credential-refs/${login.id}`);
  }
});

import { expect, test } from '@playwright/test';

/** Export a system to a .undm file and import it again under another name (D-087). */
test('export a system and import it under another name', async ({ page }) => {
  const id = String(Date.now()).slice(-6);
  const name = `Package ${id}`;
  await page.goto('/projects');
  await page.getByRole('button', { name: 'New system' }).click();
  await page.getByLabel('System name').fill(name);
  await page.getByRole('button', { name: 'Create system' }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();

  await page.getByRole('button', { name: 'Export…' }).click();
  const downloading = page.waitForEvent('download');
  await page.getByRole('dialog').getByRole('button', { name: 'Export' }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe(`Package_${id}.undm`);
  const file = await download.path();

  await page.goto('/projects');
  await page.getByRole('button', { name: 'Import…' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('input[type=file]').setInputFiles(file);
  await dialog.getByLabel('Name (optional)').fill(`${name} copy`);
  await dialog.getByRole('button', { name: 'Import' }).click();
  await expect(dialog.getByText(`Imported ${name} copy`, { exact: false })).toBeVisible();
  await dialog.getByRole('button', { name: 'Open the system' }).click();
  await expect(page.getByRole('heading', { name: `${name} copy` })).toBeVisible();
});

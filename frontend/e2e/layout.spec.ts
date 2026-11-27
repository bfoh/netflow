import { expect, test } from '@playwright/test';

import { seedSystem } from './helpers/seed';

/** No page scrolls sideways at a laptop or a phone width (D-119); tables scroll inside
 *  their own box. */
test('no page scrolls sideways', async ({ page, request }) => {
  test.setTimeout(180_000);
  const ids = await seedSystem(request);
  const urls = ['/', '/stage?choose=1', ...[0, 1, 2, 3, 4].map((s) => `/stage/${ids.projectId}?step=${s}`), '/systems',
    `/systems/${ids.projectId}`, `/systems/${ids.projectId}?tab=network`, '/devices', `/devices/${ids.deviceId}`, `/devices/${ids.deviceId}?tab=files`, `/devices/${ids.deviceId}?tab=troubleshoot`, '/firmware',
    '/console', '/plans', `/plans/new?system=${ids.projectId}`, `/plans/${ids.planId}`, '/topology', '/audit',
    ...['logins', 'templates', 'certificate', 'safety', 'identity', 'about'].map((t) => `/settings?tab=${t}`)];
  const wide: string[] = [];
  for (const url of urls) {
    await page.goto(url);
    await page.waitForLoadState('networkidle');
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (over > 1) wide.push(`${url}: ${over}px too wide`);
  }
  expect(wide, wide.join('\n')).toEqual([]);
});

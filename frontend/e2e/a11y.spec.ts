import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { seedSystem } from './helpers/seed';

/** Every page against WCAG 2.2 A and AA with axe, in light and dark (D-119). Simulated data. */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** Rules a page may still break, while it is being reworked ('*' for every page). Must end
 *  empty. */
const KNOWN: Record<string, string[]> = {};

test('every page meets WCAG 2.2 AA (axe)', async ({ page, request }) => {
  test.setTimeout(240_000);
  const ids = await seedSystem(request);
  const pages: [string, string][] = [
    ['home', '/'],
    ['stage chooser', '/stage?choose=1'],
    ...[0, 1, 2, 3, 4].map((s) => [`stage step ${s + 1}`, `/stage/${ids.projectId}?step=${s}`] as [string, string]),
    ['systems', '/systems'],
    ['system', `/systems/${ids.projectId}`],
    ['devices', '/devices'],
    ['device', `/devices/${ids.deviceId}`],
    ['firmware', '/firmware'],
    ['console tool', '/console'],
    ['plans', '/plans'],
    ['new plan', `/plans/new?system=${ids.projectId}`],
    ['plan', `/plans/${ids.planId}`],
    ['not found', '/no-such-page'],
    ['topology', '/topology'],
    ['audit', '/audit'],
    ...['logins', 'templates', 'certificate', 'safety', 'identity', 'about'].map((t) => [`settings ${t}`, `/settings?tab=${t}`] as [string, string]),
  ];
  const problems: string[] = [];
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.addInitScript((s) => window.localStorage.setItem('undm.color-scheme', s), scheme);
    for (const [name, url] of pages) {
      await page.goto(url);
      await page.waitForLoadState('networkidle');
      const result = await new AxeBuilder({ page }).withTags(TAGS).exclude('.react-flow').analyze();
      const allowed = new Set([...(KNOWN[name] ?? []), ...(KNOWN['*'] ?? [])]);
      for (const v of result.violations.filter((x) => !allowed.has(x.id))) {
        problems.push(`${scheme} · ${name} · ${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
      }
    }
  }
  expect(problems, problems.join('\n')).toEqual([]);
});

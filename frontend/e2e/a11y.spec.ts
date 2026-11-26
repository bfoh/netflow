import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { seedSystem } from './helpers/seed';

/** Every page against WCAG 2.2 A and AA with axe, in light and dark (D-119). Simulated data. */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** Rules a page may still break, while it is being reworked ('*' for every page). Must end
 *  empty. */
const KNOWN: Record<string, string[]> = {
  '*': ['aria-allowed-attr'], // the Advanced navigation group (reworked in S2)
};

test('every page meets WCAG 2.2 AA (axe)', async ({ page, request }) => {
  test.setTimeout(240_000);
  const ids = await seedSystem(request);
  const pages: [string, string][] = [
    ['home', '/'],
    ['stage chooser', '/stage?choose=1'],
    ...[0, 1, 2, 3, 4].map((s) => [`stage step ${s + 1}`, `/stage/${ids.projectId}?step=${s}`] as [string, string]),
    ['systems', '/projects'],
    ['system', `/projects/${ids.projectId}`],
    ['devices', '/devices'],
    ['device', `/devices/${ids.deviceId}`],
    ['firmware', '/firmware'],
    ['console setup', '/provisioning'],
    ['plans', '/deployments'],
    ['plan', `/deployments/${ids.planId}`],
    ['topology', '/topology'],
    ['audit', '/audit'],
    ['settings', '/settings'],
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

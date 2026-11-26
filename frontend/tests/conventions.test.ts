import { describe, expect, it } from 'vitest';

/**
 * UI conventions (D-119, D-123), checked on the source. Each count may only go down: the
 * budget is what remains to be cleaned, and it is lowered as pages are reworked.
 */
const sources = import.meta.glob('../src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const files = Object.keys(sources);
const count = (re: RegExp, skip: string[] = []) => files
  .filter((f) => !skip.some((s) => f.endsWith(s)))
  .reduce((n, f) => n + (sources[f].match(re) ?? []).length, 0);

/** What is left to clean, per rule. Lower these as pages are reworked; never raise them. */
const BUDGET = {
  colouredText: 18,
  badgeColor: 52,
  titleSize: 42,
  tableWithoutLabel: 27,
  routeStrings: 0,
  synonyms: 17,
  dismissBack: 13,
} as const;

const RULES: Record<keyof typeof BUDGET, () => number> = {
  // Warnings and errors are InlineStatus or Notice, not coloured text.
  colouredText: () => count(/<Text\b[^>]*\bc="(orange|red|yellow|teal|green)"/g),
  // Badge colours come from Tag/StateBadge/EnvironmentBadge tones.
  badgeColor: () => count(/<Badge\b[^>]*\bcolor=/g, ['components/Badges.tsx']),
  // Heading sizes come from the theme's scale, by level.
  titleSize: () => count(/<Title\b[^>]*\bsize=/g),
  // Every table is named for screen readers (DataTable does it).
  tableWithoutLabel: () => count(/<Table(?=[\s>])(?![^>]*aria-label)/g, ['components/DataTable.tsx']),
  // Routes are built in src/paths.ts (D-120); none is written out anywhere else.
  routeStrings: () => count(/(to|href)=\{?[`'"]\/(?!api)/g, ['paths.ts', 'components/nav.ts', 'routes.tsx'])
    + count(/navigate\(\s*[`'"]\//g),
  // One word for each thing (services/labels.ts).
  synonyms: () => count(/Preflight|Validate &|Retrieve information|Check information|[Cc]onsole bootstrap|secondary flash|Temporary address|credential store|[Tt]he credential\b|a credential\b|\bDeploy\b/g,
    ['services/labels.ts', 'types/api.ts']),
  // Dialogs close with Cancel (forms) or Close (read-only), not Back.
  dismissBack: () => count(/>Back<\/Button>/g),
};

describe('UI conventions (D-119, D-123)', () => {
  for (const [rule, measure] of Object.entries(RULES) as [keyof typeof BUDGET, () => number][]) {
    it(`${rule} stays within its budget (${BUDGET[rule]})`, () => {
      expect(measure()).toBeLessThanOrEqual(BUDGET[rule]);
    });
  }

  it('no "experimental" label is lost: unverified procedures stay marked (CLAUDE.md rule 7)', () => {
    expect(count(/xperimental/g)).toBeGreaterThanOrEqual(13);
  });
});

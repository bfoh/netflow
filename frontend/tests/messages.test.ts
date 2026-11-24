import { describe, expect, it } from 'vitest';

/** D-089: one message vocabulary. Message boxes come only from components/Notice.tsx. */
const sources = import.meta.glob('../src/**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

describe('messages', () => {
  it('no page draws its own banner: Notice, Hint and EmptyState only', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
    const offenders = Object.entries(sources)
      .filter(([path]) => !path.endsWith('/components/Notice.tsx'))
      .filter(([, text]) => /<Alert[\s>]/.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});

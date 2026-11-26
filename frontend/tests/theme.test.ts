import { DEFAULT_THEME, darken } from '@mantine/core';
import { describe, expect, it } from 'vitest';

import { LIGHT, SURFACES, TONE_COLORS } from '../src/theme';

/** WCAG 2.2 contrast (1.4.3 text 4.5:1, 1.4.11 controls 3:1), computed from the tokens the
 *  theme really uses, so a colour change that breaks AA fails here (D-119). */
function rgb(color: string): [number, number, number] {
  const m = color.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const [r, g, b] = m[1].split(',').map((x) => parseFloat(x));
    return [r, g, b];
  }
  const h = color.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) as [number, number, number];
}

function luminance(color: string): number {
  const [r, g, b] = rgb(color).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const C = DEFAULT_THEME.colors;

describe('the design system meets WCAG 2.2 AA (D-119)', () => {
  it('neutral text and controls, light and dark', () => {
    for (const mode of ['light', 'dark'] as const) {
      const s = SURFACES[mode];
      for (const bg of [s.body, s.subtle]) {
        expect(contrast(s.text, bg), `${mode} text`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(s.dimmed, bg), `${mode} dimmed`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(s.placeholder, bg), `${mode} placeholder`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(s.error, bg), `${mode} error text`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(s.success, bg), `${mode} success text`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(s.inputBorder, bg), `${mode} input border`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it('every tone: coloured text, filled buttons and badges on their tint', () => {
    for (const name of TONE_COLORS) {
      const t = LIGHT[name];
      expect(contrast(t.text, SURFACES.light.body), `${name} text`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.filled, '#ffffff'), `${name} filled`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.filledHover, '#ffffff'), `${name} filled hover`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.lightColor, C[name][1]), `${name} on its light tint`).toBeGreaterThanOrEqual(4.5);
      // Dark mode: Mantine's text (shade 4) on the dark body, and shade 0 on the dark tint.
      expect(contrast(C[name][4], SURFACES.dark.body), `${name} dark text`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(C[name][0], darken(C[name][9], 0.5)), `${name} dark tint`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('the focus ring and the primary colour stand out (3:1)', () => {
    expect(contrast(LIGHT.blue.filled, SURFACES.light.body)).toBeGreaterThanOrEqual(3);
    expect(contrast(LIGHT.blue.filled, SURFACES.dark.body)).toBeGreaterThanOrEqual(3);
  });
});

/**
 * UNDM's design system (D-119): one theme for every page.
 *
 * - Type: the operating system's font (Segoe UI on Windows), a fixed scale, 12 px minimum.
 * - Colour: blue for actions; every text, border, button and badge colour is chosen so that
 *   it meets WCAG 2.2 AA in light and dark (checked by tests/theme.test.ts).
 * - Status colours are used for status only (red error, orange caution, teal success, blue
 *   running/info, gray settled), always together with an icon or words.
 */
import { createTheme, type CSSVariablesResolver, DEFAULT_THEME } from '@mantine/core';

/** Colours UNDM uses for status, tags and actions. */
export const TONE_COLORS = ['blue', 'red', 'orange', 'yellow', 'teal', 'green', 'gray', 'violet', 'grape', 'cyan', 'indigo'] as const;
export type ToneColor = (typeof TONE_COLORS)[number];

interface ColorTokens {
  /** Filled buttons and badges: white text on it. */
  filled: string;
  filledHover: string;
  /** Coloured text on the page background. */
  text: string;
  /** Text on the colour's light tint (light buttons, badges, notices). */
  lightColor: string;
}

const C = DEFAULT_THEME.colors;

/** Light mode: shades that reach 4.5:1 (Mantine's defaults do not for orange, yellow, teal,
 *  green and cyan). */
export const LIGHT: Record<ToneColor, ColorTokens> = {
  blue: { filled: C.blue[8], filledHover: C.blue[9], text: C.blue[8], lightColor: C.blue[9] },
  indigo: { filled: C.indigo[8], filledHover: C.indigo[9], text: C.indigo[8], lightColor: C.indigo[9] },
  red: { filled: C.red[9], filledHover: '#a61e1e', text: C.red[9], lightColor: '#a61e1e' },
  orange: { filled: '#c2410c', filledHover: '#9a3412', text: '#a63c06', lightColor: '#9a3412' },
  yellow: { filled: '#8a5a00', filledHover: '#704a00', text: '#8a5a00', lightColor: '#6e4800' },
  teal: { filled: '#087f5b', filledHover: '#06694b', text: '#087f5b', lightColor: '#06694b' },
  green: { filled: '#1e7a34', filledHover: '#196a2d', text: '#1e7a34', lightColor: '#196a2d' },
  cyan: { filled: '#0b7285', filledHover: '#095f6f', text: '#0b7285', lightColor: '#095f6f' },
  gray: { filled: C.gray[7], filledHover: C.gray[8], text: '#5f6670', lightColor: C.gray[9] },
  violet: { filled: C.violet[8], filledHover: C.violet[9], text: C.violet[8], lightColor: C.violet[9] },
  grape: { filled: C.grape[8], filledHover: C.grape[9], text: C.grape[8], lightColor: C.grape[9] },
};

/** Surfaces and neutral text. */
export const SURFACES = {
  light: { body: '#ffffff', subtle: C.gray[0], text: C.dark[9], dimmed: '#5f6670', placeholder: '#656d75',
    inputBorder: C.gray[6], error: C.red[9], success: '#087f5b' },
  dark: { body: C.dark[7], subtle: C.dark[6], text: C.dark[0], dimmed: '#a6a6a6', placeholder: '#999999',
    inputBorder: '#7a7a7a', error: C.red[4], success: C.teal[4] },
} as const;

const FIELD_ORDER = ['label', 'input', 'description', 'error'] as const;
const FIELDS = ['TextInput', 'PasswordInput', 'NumberInput', 'Textarea', 'Select', 'MultiSelect', 'TagsInput',
  'Autocomplete', 'FileInput', 'NativeSelect', 'JsonInput'];

export const theme = createTheme({
  primaryColor: 'blue',
  primaryShade: { light: 8, dark: 8 },
  defaultRadius: 'sm',
  fontFamily: '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif',
  fontFamilyMonospace: '"Cascadia Mono", Consolas, ui-monospace, Menlo, monospace',
  headings: {
    fontWeight: '600',
    sizes: {
      h1: { fontSize: '1.625rem', lineHeight: '1.25' },
      // Section and card titles (D-123): one size per level, no size set by hand.
      h2: { fontSize: '1.125rem', lineHeight: '1.35' },
      h3: { fontSize: '1rem', lineHeight: '1.4' },
      h4: { fontSize: '0.9375rem', lineHeight: '1.4' },
      h5: { fontSize: '0.875rem', lineHeight: '1.4' },
      h6: { fontSize: '0.8125rem', lineHeight: '1.4' },
    },
  },
  components: {
    // Links are underlined, so they never depend on colour alone (WCAG 1.4.1).
    Anchor: { defaultProps: { underline: 'always' } },
    Badge: { defaultProps: { variant: 'light', radius: 'sm', tt: 'none' } },
    Card: { defaultProps: { withBorder: true, radius: 'md', padding: 'lg' } },
    Modal: { defaultProps: { centered: true, closeButtonProps: { 'aria-label': 'Close' } } },
    Drawer: { defaultProps: { closeButtonProps: { 'aria-label': 'Close' } } },
    Notification: { defaultProps: { closeButtonProps: { 'aria-label': 'Close' } } },
    Tooltip: { defaultProps: { withArrow: true, openDelay: 300, events: { hover: true, focus: true, touch: true } } },
    Table: { defaultProps: { verticalSpacing: 'sm', horizontalSpacing: 'md' } },
    // Help text sits under its field, so fields side by side line up whatever their help
    // says (forms aligned, 2026-11-27).
    ...Object.fromEntries(FIELDS.map((name) => [name, { defaultProps: { inputWrapperOrder: FIELD_ORDER } }])),
  },
});

/** The colour overrides that make Mantine's variables meet AA (see the tokens above). */
export const cssVariablesResolver: CSSVariablesResolver = () => {
  const light: Record<string, string> = {
    '--mantine-color-dimmed': SURFACES.light.dimmed,
    '--mantine-color-placeholder': SURFACES.light.placeholder,
    '--mantine-color-error': SURFACES.light.error,
    '--mantine-color-success': SURFACES.light.success,
    '--undm-input-border': SURFACES.light.inputBorder,
  };
  const dark: Record<string, string> = {
    '--mantine-color-dimmed': SURFACES.dark.dimmed,
    '--mantine-color-placeholder': SURFACES.dark.placeholder,
    '--mantine-color-error': SURFACES.dark.error,
    '--mantine-color-success': SURFACES.dark.success,
    '--undm-input-border': SURFACES.dark.inputBorder,
  };
  for (const name of TONE_COLORS) {
    const t = LIGHT[name];
    Object.assign(light, {
      [`--mantine-color-${name}-filled`]: t.filled,
      [`--mantine-color-${name}-filled-hover`]: t.filledHover,
      [`--mantine-color-${name}-text`]: t.text,
      [`--mantine-color-${name}-light-color`]: t.lightColor,
      [`--mantine-color-${name}-outline`]: t.text,
    });
    // Dark: filled buttons keep the same AA shades (white text); text and tints keep
    // Mantine's light shades, which are well above 4.5:1 on the dark body.
    Object.assign(dark, {
      [`--mantine-color-${name}-filled`]: t.filled,
      [`--mantine-color-${name}-filled-hover`]: t.filledHover,
    });
  }
  return { variables: {}, light, dark };
};

export const COLOR_SCHEME_KEY = 'undm.color-scheme';

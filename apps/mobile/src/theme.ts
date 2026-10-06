/** Which iOS blur material the glass surfaces sit on. */
export type BlurKind = 'light' | 'dark';

export const light = {
  bg: '#F6F3EE',
  bgTint: '#EDE6DB',
  card: '#FFFFFF',
  sunken: '#EFEBE4',
  text: '#3A322C',
  muted: '#8A7E74',
  primary: '#6B4F45',
  primaryText: '#FFFFFF',
  border: '#E4DDD4',
  green: '#3D9A6A',
  greenSoft: '#E7F5EE',
  danger: '#8C3A32',
  userBubble: '#E7E1D8',
  assistantBubble: '#F7F4EF',
  // Liquid glass: a translucent fill over a blur, with a bright top edge.
  blur: 'light' as BlurKind,
  glass: 'rgba(255, 255, 255, 0.55)',
  glassStrong: 'rgba(255, 255, 255, 0.74)',
  glassBorder: 'rgba(255, 255, 255, 0.9)',
  glassShadow: '#2A211B',
  scrim: 'rgba(42, 33, 27, 0.22)',
};

export const dark = {
  bg: '#1C1916',
  bgTint: '#2A2522',
  card: '#2A2522',
  sunken: '#3A332E',
  text: '#F6F3EE',
  muted: '#B7ADA4',
  primary: '#C4A894',
  primaryText: '#1C1916',
  border: '#4A433C',
  green: '#7DCEA0',
  greenSoft: '#24382E',
  danger: '#E7A39C',
  userBubble: '#3A332E',
  assistantBubble: '#26221E',
  blur: 'dark' as BlurKind,
  glass: 'rgba(58, 51, 46, 0.52)',
  glassStrong: 'rgba(58, 51, 46, 0.72)',
  glassBorder: 'rgba(255, 255, 255, 0.16)',
  glassShadow: '#000000',
  scrim: 'rgba(0, 0, 0, 0.42)',
};

export type Palette = typeof light;

/** One type scale for every screen, sized to the wireframes. */
export const typeScale = {
  display: 30,
  title: 24,
  headline: 20,
  body: 17,
  label: 16,
  caption: 15,
  micro: 13,
};

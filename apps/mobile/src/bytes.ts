import {sha256} from 'js-sha256';

const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export function toBase64(bytes: Uint8Array): string {
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i];
    const b = i + 1 < bytes.length ? bytes[i + 1] : 0;
    const c = i + 2 < bytes.length ? bytes[i + 2] : 0;
    const triple = (a << 16) | (b << 8) | c;
    out += ALPHA[(triple >> 18) & 63];
    out += ALPHA[(triple >> 12) & 63];
    out += i + 1 < bytes.length ? ALPHA[(triple >> 6) & 63] : '=';
    out += i + 2 < bytes.length ? ALPHA[triple & 63] : '=';
  }
  return out;
}

export function fromBase64(value: string): Uint8Array {
  const clean = value.replace(/[^A-Za-z0-9+/]/g, '');
  const bytes: number[] = [];
  for (let i = 0; i < clean.length; i += 4) {
    const a = ALPHA.indexOf(clean[i]);
    const b = ALPHA.indexOf(clean[i + 1]);
    const c = ALPHA.indexOf(clean[i + 2] ?? 'A');
    const d = ALPHA.indexOf(clean[i + 3] ?? 'A');
    const triple = (a << 18) | (b << 12) | (c << 6) | d;
    bytes.push((triple >> 16) & 255);
    if (i + 2 < clean.length) {
      bytes.push((triple >> 8) & 255);
    }
    if (i + 3 < clean.length) {
      bytes.push(triple & 255);
    }
  }
  return Uint8Array.from(bytes);
}

export function checksum(bytes: Uint8Array): string {
  return sha256(bytes);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${Math.round(bytes)} B`;
  }
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const shown = value >= 10 ? value.toFixed(0) : value.toFixed(1);
  return `${shown} ${units[unit]}`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)} ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

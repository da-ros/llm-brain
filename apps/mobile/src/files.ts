const IMAGE = /\.(png|jpe?g|gif|webp|heic|mp4|mov)$/i;

export function isImage(filename: string, mime: string): boolean {
  return mime.startsWith('image/') || mime.startsWith('video/') || IMAGE.test(filename);
}

export function extractText(filename: string, bytes: Uint8Array): string | null {
  if (isImage(filename, '')) {
    return null;
  }
  const raw = new TextDecoder('utf-8', {fatal: false}).decode(bytes).replace(/\u0000/g, '');
  const lower = filename.toLowerCase();
  if (lower.endsWith('.pdf') || raw.startsWith('%PDF')) {
    const parts = Array.from(raw.matchAll(/\((?:\\\)|\\.|[^\\)])*\)/g), match =>
      unescapePdf(match[0].slice(1, -1)),
    );
    const text = parts.join(' ').replace(/\s+/g, ' ').trim();
    return text || null;
  }
  const text = raw.replace(/\s+/g, ' ').trim();
  if (!text) {
    return null;
  }
  const printable = text.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]/g, '');
  if (printable.length < text.length * 0.8) {
    return null;
  }
  return text;
}

function unescapePdf(value: string): string {
  return value.replace(/\\n/g, ' ').replace(/\\r/g, ' ').replace(/\\([()\\])/g, '$1');
}

export function buildPrompt(question: string, files: {filename: string; text: string}[]): string {
  const notes = files
    .filter(file => file.text.trim())
    .map(file => `${file.filename}\n${file.text.trim()}`)
    .join('\n\n');
  return notes ? `${notes}\n\n${question}` : question;
}

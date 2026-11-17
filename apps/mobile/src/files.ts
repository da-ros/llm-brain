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

const RECORD =
  "When the question is about this person's record, answer with that fact. For any other question, answer normally.";

// The loaded context is 2048 tokens and the reply may use 1024 of them.
const PROMPT_CHAR_BUDGET = 3000;

export type PromptTurn = {role: 'user' | 'assistant' | 'note'; text: string; thinking?: string};

export function buildPrompt(
  question: string,
  files: {filename: string; text: string}[],
  history: PromptTurn[] = [],
): string {
  const notes = files
    .filter(file => file.text.trim())
    .map(file => `${file.filename}\n${file.text.trim()}`)
    .join('\n\n');
  const asked = question.trim();
  const user = notes ? `${notes}\n\n${asked}` : asked;
  const head = `<|im_start|>system\n${RECORD}<|im_end|>\n`;
  const tail = `<|im_start|>user\n${user}<|im_end|>\n<|im_start|>assistant\n<think>\n`;
  let earlier = priorExchanges(history);
  while (earlier.length > 0 && (head + earlier.join('') + tail).length > PROMPT_CHAR_BUDGET) {
    earlier = earlier.slice(1);
  }
  return head + earlier.join('') + tail;
}

function priorExchanges(history: PromptTurn[]): string[] {
  const blocks: string[] = [];
  let question = '';
  for (const turn of history) {
    if (turn.role === 'user' && turn.text.trim()) {
      question = turn.text.trim();
      continue;
    }
    if (turn.role !== 'assistant' || !question || !turn.text.trim()) {
      continue;
    }
    const thought = turn.thinking?.trim() ?? '';
    blocks.push(
      `<|im_start|>user\n${question}<|im_end|>\n` +
        `<|im_start|>assistant\n<think>\n${thought}\n</think>\n\n${turn.text.trim()}<|im_end|>\n`,
    );
    question = '';
  }
  return blocks;
}

/** Qwen puts private reasoning in <think> and the reply after </think>. */
export function splitThinking(text: string): {thinking: string; answer: string} {
  const close = text.indexOf('</think>');
  if (close === -1) {
    return {thinking: '', answer: text.trim()};
  }
  const open = text.lastIndexOf('<think>', close);
  const start = open === -1 ? 0 : open + '<think>'.length;
  const thinking = text.slice(start, close).trim();
  const answer = text.slice(close + '</think>'.length).trim();
  return {thinking, answer};
}

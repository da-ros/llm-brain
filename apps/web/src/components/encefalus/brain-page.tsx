import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowUp, CalendarDays, FileText, Menu, Paperclip, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Notice,
  PageHeader,
  Panel,
  PanelTitle,
  StatusDot,
} from "@/components/encefalus/primitives";
import { useAccount } from "@/lib/account";

type ChatThread = { id: string; title: string };
type SourceCard = { n: number; label: string; origin: "memory" | "calendar" | "attachment" };
type TurnFile = { name: string };
type Turn = {
  role: "user" | "assistant";
  text: string;
  cards?: SourceCard[];
  assumptions?: string[];
  files?: TurnFile[];
};
type Note = { date: string; note: string };

const FILE_KINDS = [
  { label: "Documents", detail: "PDF, Word, text, Markdown" },
  { label: "Spreadsheets", detail: "Excel, CSV" },
  { label: "Pages and mail", detail: "HTML, email" },
  { label: "Images", detail: "PNG, JPEG, GIF, WebP, TIFF, BMP" },
  { label: "Video", detail: "MP4, MOV, WebM, AVI, MKV" },
];

const FILE_LIMIT = 5;

const ACCEPT = [
  ".pdf",
  ".doc",
  ".docx",
  ".txt",
  ".md",
  ".markdown",
  ".ics",
  ".csv",
  ".tsv",
  ".xls",
  ".xlsx",
  ".html",
  ".htm",
  ".eml",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".tif",
  ".tiff",
  ".bmp",
  ".mp4",
  ".mov",
  ".webm",
  ".avi",
  ".mkv",
  ".mpeg",
  ".mpg",
  "image/*",
  "video/*",
].join(",");

const LIST_ITEM = /^(\*|-|\d+\.)\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const QUOTE = /^>\s?(.*)$/;
const INLINE =
  /\*\*([^*]+)\*\*|\*([^*\n]+)\*|_([^_\n]+)_|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

function lineAt(lines: string[], index: number): string {
  return lines[index] ?? "";
}

function renderInline(text: string, key: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let index = 0;
  for (const match of text.matchAll(INLINE)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    const bold = match[1];
    const italic = match[2] ?? match[3];
    const code = match[4];
    const label = match[5];
    const href = match[6];
    if (bold != null) {
      nodes.push(
        <strong key={`${key}-b${index}`} className="font-semibold">
          {bold}
        </strong>,
      );
    } else if (italic != null) {
      nodes.push(
        <em key={`${key}-i${index}`} className="italic">
          {italic}
        </em>,
      );
    } else if (code != null) {
      nodes.push(
        <code key={`${key}-c${index}`} className="rounded bg-muted px-1 font-mono text-[0.85em]">
          {code}
        </code>,
      );
    } else if (label != null && href != null) {
      nodes.push(
        <a
          key={`${key}-a${index}`}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2"
        >
          {label}
        </a>,
      );
    }
    cursor = start + match[0].length;
    index += 1;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function renderAssistantText(text: string): ReactNode {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let block = 0;

  while (i < lines.length) {
    const line = lineAt(lines, i);
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lineAt(lines, i).startsWith("```")) {
        code.push(lineAt(lines, i));
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push(
        <pre
          key={`p${block}`}
          className="overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-xs leading-5"
        >
          <code>{code.join("\n")}</code>
        </pre>,
      );
      block += 1;
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      const level = heading[1]?.length ?? 1;
      const Tag = level <= 2 ? "h3" : "h4";
      blocks.push(
        <Tag
          key={`p${block}`}
          className={level === 1 ? "text-base font-semibold" : "text-sm font-semibold"}
        >
          {renderInline(heading[2] ?? "", `p${block}`)}
        </Tag>,
      );
      i += 1;
      block += 1;
      continue;
    }
    if (QUOTE.test(line)) {
      const quoted: string[] = [];
      while (i < lines.length && QUOTE.test(lineAt(lines, i))) {
        quoted.push(lineAt(lines, i).match(QUOTE)?.[1] ?? "");
        i += 1;
      }
      blocks.push(
        <blockquote key={`p${block}`} className="border-l-2 border-border pl-3">
          {quoted.map((entry, index) => (
            <span key={index}>
              {index > 0 && <br />}
              {renderInline(entry, `p${block}-q${index}`)}
            </span>
          ))}
        </blockquote>,
      );
      block += 1;
      continue;
    }
    const item = line.match(LIST_ITEM);
    if (item) {
      const marker = item[1] ?? "";
      const ordered = /^\d+\./.test(marker);
      const items: string[] = [];
      while (i < lines.length) {
        const next = lineAt(lines, i).match(LIST_ITEM);
        const nextMarker = next?.[1] ?? "";
        if (!next || /^\d+\./.test(nextMarker) !== ordered) break;
        items.push(next[2] ?? "");
        i += 1;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag
          key={`p${block}`}
          className={ordered ? "list-decimal space-y-2 pl-5" : "list-disc space-y-2 pl-5"}
        >
          {items.map((entry, index) => (
            <li key={index}>{renderInline(entry, `p${block}-${index}`)}</li>
          ))}
        </ListTag>,
      );
      block += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length) {
      const current = lineAt(lines, i);
      if (
        current.trim() === "" ||
        current.startsWith("```") ||
        LIST_ITEM.test(current) ||
        HEADING.test(current) ||
        QUOTE.test(current)
      ) {
        break;
      }
      paragraph.push(current);
      i += 1;
    }
    blocks.push(
      <p key={`p${block}`}>
        {paragraph.map((entry, index) => (
          <span key={index}>
            {index > 0 && <br />}
            {renderInline(entry, `p${block}-l${index}`)}
          </span>
        ))}
      </p>,
    );
    block += 1;
  }

  return <div className="space-y-3 text-sm leading-6">{blocks}</div>;
}

function authHeaders(): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (response.status === 401) return "Sign in with a premium token to use Brain.";
  return "Brain could not complete that request.";
}

export function BrainPage() {
  const account = useAccount();
  const premium = account?.plan === "premium";
  const skipLoad = useRef(new Set<string>());
  const [chats, setChats] = useState<ChatThread[]>([]);
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [threads, setThreads] = useState<Record<string, Turn[]>>({});
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<{ name: string; base64: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState(() => new Date());
  const [selected, setSelected] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const openChats = openIds
    .map((id) => chats.find((chat) => chat.id === id))
    .filter((chat): chat is ChatThread => Boolean(chat));
  const turns = activeId ? (threads[activeId] ?? []) : [];
  const latest = [...turns].reverse().find((turn) => turn.role === "assistant");
  const cards = latest?.cards ?? [];

  useEffect(() => {
    void loadChats();
  }, []);

  useEffect(() => {
    if (!premium) return;
    void loadNotes(cursor);
  }, [cursor, premium]);

  useEffect(() => {
    if (!activeId || skipLoad.current.has(activeId)) return;
    void loadTurns(activeId);
  }, [activeId]);

  useEffect(() => {
    const pane = threadRef.current;
    if (!pane) return;
    pane.scrollTop = pane.scrollHeight;
  }, [turns.length, activeId]);

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "0px";
    composer.style.height = `${Math.min(composer.scrollHeight, 160)}px`;
  }, [message]);

  async function loadChats() {
    const response = await fetch("/api/chats", { headers: authHeaders() });
    if (!response.ok) return;
    const body = await response.json();
    const rows = (body.chats ?? []) as ChatThread[];
    setChats(rows);
    setOpenIds((current) => {
      const live = current.filter((id) => rows.some((row) => row.id === id));
      if (live.length > 0) return live;
      return rows[0] ? [rows[0].id] : [];
    });
    setActiveId((current) => {
      if (current && rows.some((row) => row.id === current)) return current;
      return rows[0]?.id ?? null;
    });
  }

  function showChat(chatId: string) {
    setOpenIds((current) => (current.includes(chatId) ? current : [...current, chatId]));
    setActiveId(chatId);
    setMenuOpen(false);
  }

  function closeTab(chatId: string) {
    setOpenIds((current) => {
      const rest = current.filter((id) => id !== chatId);
      setActiveId((active) => (active === chatId ? (rest.at(-1) ?? null) : active));
      return rest;
    });
  }

  async function loadTurns(chatId: string) {
    try {
      const response = await fetch(`/api/chats/${chatId}/turns`, { headers: authHeaders() });
      if (!response.ok) return;
      const body = await response.json();
      setThreads((current) => ({ ...current, [chatId]: (body.turns ?? []) as Turn[] }));
    } catch {
      return;
    }
  }

  async function loadNotes(month: Date) {
    const start = iso(month.getFullYear(), month.getMonth(), 1);
    const end = iso(month.getFullYear(), month.getMonth(), daysInMonth(month));
    setSelected((current) => (current.startsWith(start.slice(0, 7)) ? current : start));
    try {
      const response = await fetch(`/api/calendar?start=${start}&end=${end}`, {
        headers: authHeaders(),
      });
      if (!response.ok) return;
      const body = await response.json();
      const next: Record<string, string> = {};
      for (const row of (body.notes ?? []) as Note[]) next[row.date] = row.note;
      setNotes(next);
    } catch {
      return;
    }
  }

  async function newChat() {
    setError("");
    let response: Response;
    try {
      response = await fetch("/api/chats", { method: "POST", headers: authHeaders() });
    } catch {
      setError("Brain is not reachable. Start the API router and sign in.");
      return;
    }
    if (!response.ok) {
      setError(await readError(response));
      return;
    }
    const chat = (await response.json()) as ChatThread;
    setChats((rows) => [chat, ...rows]);
    setThreads((current) => ({ ...current, [chat.id]: [] }));
    showChat(chat.id);
  }

  async function deleteChat(chatId: string) {
    setError("");
    try {
      const response = await fetch(`/api/chats/${chatId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
    } catch {
      setError("Brain is not reachable. Start the API router and sign in.");
      return;
    }
    setChats((rows) => rows.filter((chat) => chat.id !== chatId));
    setThreads((current) => {
      const next = { ...current };
      delete next[chatId];
      return next;
    });
    closeTab(chatId);
    setMenuOpen(false);
  }

  async function renameChat(chatId: string) {
    const title = renameDraft.trim();
    if (!title) return;
    setError("");
    try {
      const response = await fetch(`/api/chats/${chatId}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ title }),
      });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      const chat = (await response.json()) as ChatThread;
      setChats((rows) => rows.map((row) => (row.id === chatId ? { ...row, title: chat.title } : row)));
      setRenamingId(null);
    } catch {
      setError("Brain is not reachable. Start the API router and sign in.");
    }
  }

  async function saveNote(day: string, note: string) {
    setNotes((current) => ({ ...current, [day]: note }));
    setNoteSaved(false);
    try {
      const response = await fetch(`/api/calendar/${day}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ note }),
      });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      setNoteSaved(true);
    } catch {
      setError("Brain is not reachable. Start the API router and sign in.");
    }
  }

  async function send() {
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    let chatId = activeId;
    if (!chatId) {
      try {
        const created = await fetch("/api/chats", { method: "POST", headers: authHeaders() });
        if (!created.ok) {
          setError(await readError(created));
          setBusy(false);
          return;
        }
        const chat = (await created.json()) as ChatThread;
        chatId = chat.id;
        skipLoad.current.add(chat.id);
        setChats((rows) => [chat, ...rows]);
        showChat(chat.id);
      } catch {
        setError("Brain is not reachable. Start the API router and sign in.");
        setBusy(false);
        return;
      }
    }
    const attached = files;
    setThreads((current) => ({
      ...current,
      [chatId]: [
        ...(current[chatId] ?? []),
        { role: "user", text, files: attached.map((item) => ({ name: item.name })) },
      ],
    }));
    setMessage("");
    setFiles([]);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          message: text,
          use_rag: premium,
          session_id: chatId,
          ...(attached.length
            ? {
                attachments: attached.map((item) => ({
                  filename: item.name,
                  content_base64: item.base64,
                })),
              }
            : {}),
        }),
      });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      const body = await response.json();
      const answer: Turn = {
        role: "assistant",
        text: body.response ?? "",
        cards: body.source_cards ?? [],
        assumptions: body.assumptions ?? [],
      };
      setThreads((current) => ({ ...current, [chatId]: [...(current[chatId] ?? []), answer] }));
      await loadChats();
    } catch {
      setError("Brain is not reachable. Start the API router and sign in.");
    } finally {
      if (chatId) skipLoad.current.delete(chatId);
      setBusy(false);
    }
  }

  async function onFile(list: FileList | null) {
    const picked = [...(list ?? [])];
    if (picked.length === 0) return;
    if (files.length + picked.length > FILE_LIMIT) {
      setError("You can attach up to five files for one question.");
      return;
    }
    setError("");
    try {
      const next = await Promise.all(picked.map(readFile));
      setFiles((current) => [...current, ...next].slice(0, FILE_LIMIT));
    } catch {
      setError("That file could not be read.");
    }
  }

  const cells = useMemo(() => monthCells(cursor), [cursor]);

  return (
    <main className="flex h-[calc(100svh-3.5rem)] flex-col overflow-hidden lg:h-svh">
      <PageHeader
        className="shrink-0"
        eyebrow="Personal cognitive workspace"
        title="Brain"
        description="Ask in a chat. Answers use your memory and calendar notes, and say where they came from."
        action={<StatusDot label="Personal Brain online" />}
      />
      <div className="grid min-h-0 flex-1 xl:grid-cols-[minmax(0,1fr)_310px]">
        <section className="flex min-h-0 min-w-0 flex-col border-r border-border">
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3">
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                aria-label="List chats"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((open) => !open)}
              >
                <Menu />
              </Button>
              {menuOpen && (
                <div className="absolute left-0 top-11 z-20 w-72 rounded-lg border border-border bg-card p-1 shadow-panel">
                  {chats.length === 0 && (
                    <p className="px-3 py-2 text-xs text-muted-foreground">No chats yet.</p>
                  )}
                  {chats.map((chat) => (
                    <div key={chat.id} className="flex items-center gap-1">
                      {renamingId === chat.id ? (
                        <input
                          value={renameDraft}
                          autoFocus
                          aria-label={`Rename ${chat.title}`}
                          onChange={(event) => setRenameDraft(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") void renameChat(chat.id);
                            if (event.key === "Escape") setRenamingId(null);
                          }}
                          className="min-w-0 flex-1 rounded-md border border-border bg-transparent px-2 py-1 text-xs outline-none"
                        />
                      ) : (
                        <button
                          type="button"
                          onClick={() => showChat(chat.id)}
                          className="min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left text-xs font-semibold hover:bg-muted"
                        >
                          {chat.title}
                        </button>
                      )}
                      {renamingId !== chat.id && (
                        <button
                          type="button"
                          aria-label={`Rename ${chat.title}`}
                          className="shrink-0 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
                          onClick={() => {
                            setRenamingId(chat.id);
                            setRenameDraft(chat.title);
                          }}
                        >
                          Rename
                        </button>
                      )}
                      <button
                        type="button"
                        aria-label={`Delete ${chat.title}`}
                        className="shrink-0 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
                        onClick={() => void deleteChat(chat.id)}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
              {openChats.map((chat) => (
                <span
                  key={chat.id}
                  className={`flex shrink-0 items-center rounded-md ${chat.id === activeId ? "bg-card shadow-sm" : "text-muted-foreground"}`}
                >
                  <button
                    type="button"
                    onClick={() => setActiveId(chat.id)}
                    className="max-w-40 truncate px-3 py-1.5 text-xs font-semibold"
                  >
                    {chat.title}
                  </button>
                  <button
                    type="button"
                    aria-label={`Close ${chat.title}`}
                    className="pr-2 text-xs text-muted-foreground"
                    onClick={() => closeTab(chat.id)}
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            </div>
            <Button variant="outline" size="sm" className="shrink-0" onClick={() => void newChat()}>
              <Plus />
              New chat
            </Button>
          </div>
          <div
            ref={threadRef}
            className="min-h-0 flex-1 overflow-y-auto"
          >
          <div className="mx-auto flex w-full max-w-3xl flex-col px-4 py-8 sm:px-7">
            {turns.length === 0 && (
              <p className="text-sm leading-6 text-muted-foreground">
                Start a chat. Attached files stay in this chat for later questions and are not saved
                to Memory.
              </p>
            )}
            <div className="space-y-7">
              {turns.map((turn, index) =>
                turn.role === "user" ? (
                  <div
                    key={index}
                    className="ml-auto max-w-lg rounded-lg border border-border bg-muted px-4 py-3 text-sm"
                  >
                    {!!turn.files?.length && (
                      <div className="mb-2 flex flex-wrap justify-end gap-2">
                        {turn.files.map((file, fileIndex) => (
                          <span
                            key={`${file.name}-${fileIndex}`}
                            className="inline-flex max-w-36 flex-col items-center gap-0.5"
                          >
                            <FileText className="size-4 text-primary" />
                            <span className="w-full truncate text-center text-[10px] leading-3">
                              {file.name}
                            </span>
                          </span>
                        ))}
                      </div>
                    )}
                    {turn.text}
                  </div>
                ) : (
                  <div key={index} className="flex gap-3">
                    <img
                      src="/encefalus-mark.png"
                      alt=""
                      className="size-8 shrink-0 rounded-lg"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="mb-2 text-sm font-semibold">Encefalus</p>
                      {renderAssistantText(turn.text)}
                      {!!turn.cards?.length && (
                        <div className="mt-5 flex flex-wrap gap-2">
                          {turn.cards.map((card) => (
                            <SourceCardView key={card.n} card={card} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>
            </div>
          </div>
          <div className="shrink-0 border-t border-border bg-background px-4 py-3 sm:px-7">
            <div className="mx-auto w-full max-w-3xl">
              {error && (
                <div className="mb-3">
                  <Notice>{error}</Notice>
                </div>
              )}
              <div className="rounded-lg border border-input bg-card p-2 shadow-panel">
                <textarea
                  ref={composerRef}
                  rows={1}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                  placeholder="Ask your Brain…"
                  className="max-h-40 min-h-7 w-full resize-none overflow-y-auto bg-transparent px-2 py-1 text-sm leading-5 outline-none placeholder:text-muted-foreground"
                />
                {files.length > 0 && (
                  <ul className="mb-1 flex flex-wrap gap-1.5 px-1">
                    {files.map((item, index) => (
                      <li
                        key={`${item.name}-${index}`}
                        className="flex max-w-full items-center gap-1 rounded-md bg-muted px-2 py-1 text-[11px]"
                      >
                        <span className="truncate">{item.name}</span>
                        <button
                          type="button"
                          className="text-muted-foreground"
                          aria-label={`Remove ${item.name}`}
                          onClick={() =>
                            setFiles((current) =>
                              current.filter((_, itemIndex) => itemIndex !== index),
                            )
                          }
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Attach files"
                    onClick={() => fileRef.current?.click()}
                  >
                    <Paperclip />
                  </Button>
                  <span className="truncate text-right text-[11px] text-muted-foreground">
                    {files.length
                      ? `${files.length} of ${FILE_LIMIT} files · kept in this chat, not saved to Memory`
                      : premium
                        ? "Personal Brain · Memory on"
                        : "Up to five files for this question · not saved to Memory"}
                  </span>
                  <Button
                    size="icon"
                    aria-label="Send"
                    disabled={busy || !message.trim()}
                    onClick={() => void send()}
                  >
                    <ArrowUp />
                  </Button>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept={ACCEPT}
                  multiple
                  className="hidden"
                  onChange={(event) => {
                    void onFile(event.target.files);
                    event.target.value = "";
                  }}
                />
              </div>
              <ul className="mt-3 flex flex-wrap gap-2">
                {FILE_KINDS.map((kind) => (
                  <li
                    key={kind.label}
                    className="rounded-md border border-border bg-card px-2 py-1 text-[11px] leading-4"
                  >
                    <span className="font-semibold">{kind.label}</span>
                    <span className="text-muted-foreground"> · {kind.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
        <aside className="min-h-0 overflow-y-auto bg-card/45 p-5">
          <h2 className="text-sm font-semibold">Context used</h2>
          <div className="mt-4 space-y-3">
            <Panel>
              <PanelTitle
                title="Sources"
                aside={
                  <StatusDot
                    label={`${cards.length} ${cards.length === 1 ? "source" : "sources"}`}
                  />
                }
              />
              <p className="p-4 text-xs leading-5 text-muted-foreground">
                {cards.length
                  ? "Memory, calendar notes, and files attached to this question."
                  : "No sources on this answer yet."}
              </p>
            </Panel>
            <Panel>
              <PanelTitle title="General model knowledge" />
              <p className="p-4 text-xs leading-5 text-muted-foreground">
                Used only to organize and explain your personal context.
              </p>
            </Panel>
          </div>
          <h3 className="mt-7 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Calendar
          </h3>
          {!premium ? (
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              Calendar notes are on the Premium plan.
            </p>
          ) : (
            <div className="mt-3 rounded-lg border border-border bg-card p-3">
              <div className="mb-2 flex items-center justify-between text-xs font-semibold">
                <button
                  type="button"
                  className="px-1"
                  onClick={() => setCursor(shiftMonth(cursor, -1))}
                  aria-label="Previous month"
                >
                  ‹
                </button>
                <span>{cursor.toLocaleString("en", { month: "long", year: "numeric" })}</span>
                <button
                  type="button"
                  className="px-1"
                  onClick={() => setCursor(shiftMonth(cursor, 1))}
                  aria-label="Next month"
                >
                  ›
                </button>
              </div>
              <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-muted-foreground">
                {["S", "M", "T", "W", "T", "F", "S"].map((label, index) => (
                  <span key={`${label}-${index}`}>{label}</span>
                ))}
                {cells.map((day, index) =>
                  day ? (
                    <button
                      key={day}
                      type="button"
                      onClick={() => {
                        setSelected(day);
                        setNoteSaved(false);
                      }}
                      className={`rounded py-1 text-xs ${day === selected ? "bg-primary text-primary-foreground" : notes[day] ? "bg-muted font-semibold" : ""}`}
                    >
                      {Number(day.slice(8))}
                    </button>
                  ) : (
                    <span key={`pad-${index}`} />
                  ),
                )}
              </div>
              {selected && (
                <>
                  <textarea
                    value={notes[selected] ?? ""}
                    onChange={(event) => {
                      setNoteSaved(false);
                      setNotes((current) => ({ ...current, [selected]: event.target.value }));
                    }}
                    placeholder="Note for this day"
                    className="mt-3 min-h-16 w-full resize-none rounded-md border border-border bg-transparent p-2 text-xs outline-none"
                  />
                  <Button
                    size="sm"
                    className="mt-2 w-full"
                    onClick={() => void saveNote(selected, notes[selected] ?? "")}
                  >
                    Save note
                  </Button>
                  {noteSaved && (
                    <p className="mt-1 text-[11px] text-muted-foreground">Saved for this day.</p>
                  )}
                </>
              )}
            </div>
          )}
          <h3 className="mt-7 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Evidence
          </h3>
          <ul className="mt-3 space-y-3 text-xs">
            {cards.length === 0 && (
              <li className="text-muted-foreground">Sources show up here after an answer.</li>
            )}
            {cards.map((card) => (
              <li key={card.n}>
                {card.n}. {card.label} · {sourceNote(card.origin)}
              </li>
            ))}
          </ul>
          <h3 className="mt-7 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Assumptions
          </h3>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            {latest?.assumptions?.length
              ? latest.assumptions.join(" ")
              : "Assumptions from the answer appear here."}
          </p>
        </aside>
      </div>
    </main>
  );
}

function readFile(file: File): Promise<{ name: string; base64: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result ?? "");
      const base64 = raw.includes(",") ? raw.slice(raw.indexOf(",") + 1) : raw;
      resolve({ name: file.name, base64 });
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function sourceNote(origin: SourceCard["origin"]) {
  if (origin === "calendar") return "From your calendar";
  if (origin === "attachment") return "Attached to this question";
  return "From your memory";
}

function SourceCardView({ card }: { card: SourceCard }) {
  const Icon =
    card.origin === "calendar" ? CalendarDays : card.origin === "attachment" ? Paperclip : FileText;
  return (
    <div className="flex min-w-0 max-w-full items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-left sm:max-w-[16rem]">
      <span className="text-primary">
        <Icon className="size-3.5" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[11px] font-semibold leading-4">
          {card.n}. {card.label}
        </span>
        <span className="block truncate text-[10px] leading-3 text-muted-foreground">
          {sourceNote(card.origin)}
        </span>
      </span>
    </div>
  );
}

function daysInMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth() + 1, 0).getDate();
}

function iso(year: number, month: number, day: number) {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function shiftMonth(value: Date, delta: number) {
  return new Date(value.getFullYear(), value.getMonth() + delta, 1);
}

function monthCells(value: Date): Array<string | null> {
  const year = value.getFullYear();
  const month = value.getMonth();
  const pad = new Date(year, month, 1).getDay();
  const cells: Array<string | null> = Array.from({ length: pad }, () => null);
  for (let day = 1; day <= daysInMonth(value); day += 1) cells.push(iso(year, month, day));
  return cells;
}

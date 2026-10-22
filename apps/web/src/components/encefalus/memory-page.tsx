import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Plus,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Notice,
  PageHeader,
  Panel,
  PremiumNotice,
  StatusDot,
} from "@/components/encefalus/primitives";
import { useAccount } from "@/lib/account";

type Kind = "document" | "image" | "video";
type MemoryFile = {
  id: string;
  name: string;
  kind: Kind;
  content_type?: string;
  added: string;
  status: "Processing" | "Distilled" | "Embedded";
  summary: string;
};
type Counts = { document: number; image: number; video: number };

const EMPTY_COUNTS: Counts = { document: 0, image: 0, video: 0 };
const SPREADSHEET_NAME = /\.(csv|tsv|xls|xlsx)$/i;
const SPREADSHEET_TYPES = new Set([
  "text/csv",
  "text/tab-separated-values",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]);

function authHeaders(): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (response.status === 401) return "Sign in with a premium token to use Memory.";
  return "Memory could not be loaded.";
}

export function MemoryPage() {
  const account = useAccount();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | Kind>("all");
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [counts, setCounts] = useState<Counts>(EMPTY_COUNTS);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const selected = files.find((file) => file.id === selectedId) ?? files[0];

  useEffect(() => {
    const handle = window.setTimeout(() => void load(query, kind), 200);
    return () => window.clearTimeout(handle);
  }, [query, kind]);

  useEffect(() => {
    if (!files.some((file) => file.status === "Processing" || file.status === "Distilled")) return;
    const handle = window.setInterval(() => void load(query, kind), 4000);
    return () => window.clearInterval(handle);
  }, [files, query, kind]);

  async function load(text: string, filter: "all" | Kind) {
    const params = new URLSearchParams();
    if (filter !== "all") params.set("kind", filter);
    const path = text.trim()
      ? `/api/documents/search?q=${encodeURIComponent(text.trim())}${params.size ? `&${params}` : ""}`
      : `/api/documents${params.size ? `?${params}` : ""}`;
    try {
      const response = await fetch(path, { headers: authHeaders() });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      const body = await response.json();
      const rows = (body.documents ?? []) as MemoryFile[];
      setFiles(rows);
      setCounts(body.counts ?? EMPTY_COUNTS);
      setError("");
      const focus = focusedMemory();
      const match = focus ? rows.find((row) => sameMemory(row, focus)) : undefined;
      setSelectedId((current) => {
        if (match) return match.id;
        if (rows.some((row) => row.id === current)) return current;
        return rows[0]?.id ?? "";
      });
    } catch {
      setError("Memory is not reachable. Start the API router and sign in.");
    }
  }

  if (account?.plan === "free") return <PremiumNotice title="Memory" />;

  return (
    <main className="min-h-svh">
      <PageHeader
        eyebrow="Personal knowledge"
        title="Memory"
        description="Find and manage the information your Brain can remember."
        action={<UploadDialog onUploaded={() => void load(query, kind)} />}
      />
      <div className="grid xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="min-w-0 border-r border-border p-5 sm:p-7">
          <label className="flex h-10 items-center gap-2 rounded-md border border-input bg-card px-3">
            <Search className="size-4 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              placeholder="Search your memories…"
            />
          </label>
          <div className="mt-4 flex gap-1 overflow-x-auto">
            <KindButton
              label="All"
              count={counts.document + counts.image + counts.video}
              active={kind === "all"}
              onClick={() => setKind("all")}
            />
            <KindButton
              label="Document"
              count={counts.document}
              active={kind === "document"}
              onClick={() => setKind("document")}
            />
            <KindButton
              label="Image"
              count={counts.image}
              active={kind === "image"}
              onClick={() => setKind("image")}
            />
            <KindButton
              label="Video"
              count={counts.video}
              active={kind === "video"}
              onClick={() => setKind("video")}
            />
          </div>
          {error && (
            <div className="mt-4">
              <Notice>{error}</Notice>
            </div>
          )}
          <Panel className="mt-5 overflow-hidden">
            <div className="hidden grid-cols-[minmax(0,1.5fr)_1fr_1fr_auto] gap-3 border-b border-border bg-muted/40 px-4 py-2 text-[10px] font-semibold uppercase text-muted-foreground sm:grid">
              <span>Name</span>
              <span>Type</span>
              <span>Added</span>
              <span>Status</span>
            </div>
            {files.length === 0 && (
              <p className="px-4 py-6 text-sm text-muted-foreground">No files in this view.</p>
            )}
            {files.map((file) => {
              const Icon = fileIcon(file);
              return (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => setSelectedId(file.id)}
                  className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-4 py-3 text-left last:border-0 sm:grid-cols-[minmax(0,1.5fr)_1fr_1fr_auto] ${selected?.id === file.id ? "bg-accent/60" : "hover:bg-muted/50"}`}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Icon className="size-4 shrink-0 text-primary" />
                    <span className="truncate text-sm font-medium">{file.name}</span>
                  </span>
                  <span className="hidden text-xs capitalize text-muted-foreground sm:block">
                    {file.kind}
                  </span>
                  <span className="hidden text-xs text-muted-foreground sm:block">
                    {formatAdded(file.added)}
                  </span>
                  <StatusDot
                    tone={
                      file.status === "Processing"
                        ? "warn"
                        : file.status === "Distilled"
                          ? "neutral"
                          : "good"
                    }
                    label={file.status}
                  />
                </button>
              );
            })}
          </Panel>
        </section>
        <aside className="bg-card/45 p-5">
          {selected ? (
            <Detail
              file={selected}
              onDelete={async (id) => {
                const response = await fetch(`/api/documents/${encodeURIComponent(id)}`, {
                  method: "DELETE",
                  headers: authHeaders(),
                });
                if (!response.ok) {
                  throw new Error(await readError(response));
                }
                await load(query, kind);
              }}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Select a file to see its summary.</p>
          )}
        </aside>
      </div>
    </main>
  );
}

function focusedMemory() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("file") ?? "";
}

function sameMemory(file: MemoryFile, focus: string) {
  const needle = focus.trim().toLowerCase();
  const name = file.name.trim().toLowerCase();
  const base = needle.split(/[/\\]/).pop() ?? needle;
  return file.id.toLowerCase() === needle || name === needle || name === base;
}

function fileIcon(file: MemoryFile) {
  if (file.kind === "image") return FileImage;
  if (file.kind === "video") return FileVideo;
  const type = (file.content_type ?? "").toLowerCase();
  if (SPREADSHEET_TYPES.has(type) || SPREADSHEET_NAME.test(file.name)) return FileSpreadsheet;
  return FileText;
}

function Detail({
  file,
  onDelete,
}: {
  file: MemoryFile;
  onDelete: (id: string) => Promise<void>;
}) {
  const Icon = fileIcon(file);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    setConfirming(false);
    setDeleteError("");
    setBusy(false);
  }, [file.id]);

  async function remove() {
    setBusy(true);
    setDeleteError("");
    try {
      await onDelete(file.id);
    } catch (exc) {
      setDeleteError(exc instanceof Error ? exc.message : "That file could not be deleted.");
      setBusy(false);
    }
  }

  return (
    <>
      <div className="flex items-center gap-3">
        <Icon className="size-5 text-primary" />
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{file.name}</h2>
          <p className="text-[10px] capitalize text-muted-foreground">{file.kind}</p>
        </div>
      </div>
      <h3 className="mt-6 text-xs font-semibold">Extracted summary</h3>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{summaryText(file)}</p>
      <dl className="mt-5 grid grid-cols-2 gap-y-3 text-xs">
        <dt className="text-muted-foreground">Added</dt>
        <dd>{formatAdded(file.added)}</dd>
        <dt className="text-muted-foreground">Status</dt>
        <dd>{file.status}</dd>
      </dl>
      <Button asChild className="mt-6 w-full">
        <Link to="/brain">Ask Brain about this</Link>
      </Button>
      {confirming ? (
        <div className="mt-3">
          <p className="text-xs leading-5 text-muted-foreground">
            Remove this file from Memory? Brain will stop using it.
          </p>
          <div className="mt-2 flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              disabled={busy}
              onClick={() => void remove()}
            >
              <Trash2 />
              {busy ? "Deleting…" : "Delete"}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="outline" className="mt-3 w-full" onClick={() => setConfirming(true)}>
          <Trash2 />
          Delete memory
        </Button>
      )}
      {deleteError && (
        <div className="mt-3">
          <Notice>{deleteError}</Notice>
        </div>
      )}
    </>
  );
}

function KindButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Button size="sm" variant={active ? "secondary" : "ghost"} onClick={onClick}>
      {label} ({count})
    </Button>
  );
}

function UploadDialog({ onUploaded }: { onUploaded: () => void }) {
  const [error, setError] = useState("");

  async function upload(list: FileList | null) {
    const file = list?.[0];
    if (!file) return;
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/api/upload", { method: "POST", headers: authHeaders(), body });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      onUploaded();
    } catch {
      setError("Memory is not reachable. Start the API router and sign in.");
    }
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          Add memory
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add to your Brain</DialogTitle>
          <DialogDescription>
            Documents, images, and video become searchable personal context.
          </DialogDescription>
        </DialogHeader>
        <label className="mt-2 grid min-h-64 cursor-pointer place-items-center rounded-lg border border-dashed border-input bg-muted/30 p-8 text-center">
          <input
            className="sr-only"
            type="file"
            onChange={(event) => void upload(event.target.files)}
          />
          <span>
            <Upload className="mx-auto size-7 text-primary" />
            <b className="mt-4 block text-sm">Choose a file</b>
            <span className="mt-2 block text-xs leading-5 text-muted-foreground">
              PDF, Word, text, images, and video
            </span>
          </span>
        </label>
        {error && (
          <div className="mt-3">
            <Notice>{error}</Notice>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function summaryText(file: MemoryFile) {
  if (file.summary) return file.summary;
  if (file.status === "Processing") return "This file is still in the queue.";
  if (file.status === "Distilled")
    return "Facts were extracted. They are not searchable until embedding finishes.";
  return "No summary was extracted.";
}

function formatAdded(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" });
}

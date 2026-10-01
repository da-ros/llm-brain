import { useEffect, useState, type ClipboardEvent } from "react";
import { AlertTriangle, CheckCircle2, FileUp, Search, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice, PageHeader, Panel, PanelTitle, PremiumNotice, StatusDot } from "@/components/encefalus/primitives";
import { useAccount } from "@/lib/account";

type Reason = { type?: string; id?: string; detail?: string; label?: string };
type Scan = {
  id: string;
  summary: string;
  severity: string;
  rationale: string;
  reasons?: Reason[];
  source?: string;
};

const EVIDENCE: Record<string, string> = {
  urgency: "Creates a false sense of urgency.",
  credential: "Requests sensitive account credentials.",
  money: "Asks for payment, a gift card, or cryptocurrency.",
  short_url: "Uses a shortened link.",
  prize: "Offers a prize or lottery win.",
  lookalike_host: "Domain resembles a known service but is not an official domain.",
  embedding_unavailable: "A similarity check against known examples was not available.",
  ocr_empty: "No text could be read from the image.",
};

const SOURCES = [
  { id: "email", label: "Email", source: "email" },
  { id: "sms", label: "SMS", source: "sms" },
  { id: "website", label: "Website", source: "message" },
  { id: "social", label: "Social message", source: "message" },
] as const;

const MAX_BYTES = 20 * 1024 * 1024;

function authHeaders(json = false): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (response.status === 401 || response.status === 403) {
    return "Sign in with a premium token to use Shield.";
  }
  return fallback;
}

function tone(severity: string): "good" | "warn" | "bad" | "neutral" {
  const value = severity.toLowerCase();
  if (value === "high") return "bad";
  if (value === "medium") return "warn";
  if (value === "low" || value === "none") return "good";
  return "neutral";
}

function severityLabel(severity: string) {
  const value = (severity || "").toLowerCase();
  if (value === "none" || value === "low") return "Low";
  if (value === "medium") return "Medium";
  if (value === "high") return "High";
  return severity || "Unknown";
}

export function ShieldPage() {
  const account = useAccount();
  const [text, setText] = useState("");
  const [sourceId, setSourceId] = useState<(typeof SOURCES)[number]["id"]>("email");
  const [file, setFile] = useState<File | null>(null);
  const [scans, setScans] = useState<Scan[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = scans.find((scan) => scan.id === selectedId) ?? null;

  function takeScreenshot(event: ClipboardEvent) {
    const items = event.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (!item.type.startsWith("image/")) continue;
      const pasted = item.getAsFile();
      if (!pasted) return;
      const name = pasted.name && pasted.name !== "image.png" ? pasted.name : "screenshot.png";
      event.preventDefault();
      setFile(new File([pasted], name, { type: pasted.type || "image/png" }));
      return;
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const response = await fetch("/api/shield/incidents", { headers: authHeaders() });
      if (!response.ok) {
        setError(await readError(response, "Shield could not be loaded."));
        return;
      }
      const body = await response.json();
      const rows = (body.incidents ?? []) as Scan[];
      setScans(rows);
      setError("");
      setSelectedId((current) => (rows.some((row) => row.id === current) ? current : ""));
    } catch {
      setError("Shield is not reachable. Start the API router and sign in.");
    }
  }

  async function scan() {
    const pasted = text.trim();
    if ((!pasted && !file) || busy) return;
    if (file && file.size > MAX_BYTES) {
      setError("That file is larger than 20 MB.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const chosen = SOURCES.find((item) => item.id === sourceId) ?? SOURCES[0];
      const payload: Record<string, string> = { text: pasted, source: chosen.source };
      if (file) {
        payload.filename = file.name;
        payload.content_base64 = await readBase64(file);
        if (file.type.startsWith("image/")) payload.source = "image";
        else if (file.type.startsWith("video/")) payload.source = "video";
      }
      const response = await fetch("/api/shield/scan", {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        setError(await readError(response, "The scan could not be completed."));
        setBusy(false);
        return;
      }
      const body = await response.json();
      const row: Scan = {
        id: body.incident_id || "",
        summary: body.summary || "Scan",
        severity: body.severity || "",
        rationale: body.rationale || "",
        reasons: body.reasons ?? [],
        source: payload.source,
      };
      if (row.id) {
        setScans((current) => [row, ...current.filter((item) => item.id !== row.id)]);
        setSelectedId(row.id);
      }
      await load();
      if (row.id) setSelectedId(row.id);
    } catch {
      setError("Shield is not reachable. Start the API router and sign in.");
    }
    setBusy(false);
  }

  if (account?.plan === "free") return <PremiumNotice title="Shield" />;

  return (
    <main className="min-h-svh">
      <PageHeader
        eyebrow="Privacy and scam protection"
        title="Shield"
        description="Inspect suspicious content and understand the evidence behind each risk assessment."
      />
      <div className="grid xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="border-r border-border p-5 sm:p-7" onPaste={takeScreenshot}>
          <h2 className="text-lg font-bold">Scan suspicious content</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste an email, SMS, message, or link. You can also attach an image or video.
          </p>
          {error && (
            <div className="mt-4">
              <Notice>{error}</Notice>
            </div>
          )}
          <label className="mt-6 block text-xs font-semibold">
            Content to scan
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste the message here."
              className="mt-2 min-h-44 w-full resize-none rounded-lg border border-input bg-card p-4 text-sm font-normal leading-6 outline-none focus:ring-1 focus:ring-ring"
            />
          </label>
          <p className="mt-4 text-xs leading-5 text-muted-foreground">
            Paste the message and a picture together, or paste a screenshot on its own.
          </p>
          <label className="mt-3 flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-input bg-card p-4">
            <FileUp className="size-5 text-primary" />
            <span>
              <b className="block text-xs">{file ? file.name : "Add attachment"}</b>
              <span className="text-[11px] text-muted-foreground">Image or video · max 20 MB</span>
            </span>
            <input
              type="file"
              accept="image/*,video/*"
              className="sr-only"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div className="mt-5 grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)]">
            <select
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value as (typeof SOURCES)[number]["id"])}
              className="h-10 rounded-md border border-input bg-card px-3 text-sm outline-none"
            >
              {SOURCES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            <Button disabled={busy || (!text.trim() && !file)} onClick={() => void scan()}>
              <Search />
              {busy ? "Scanning…" : "Scan for risks"}
            </Button>
          </div>
          <Panel className="mt-8">
            <PanelTitle title="Recent scans" aside={<span className="text-[11px] text-muted-foreground">{scans.length}</span>} />
            {scans.length === 0 ? (
              <p className="px-4 py-3 text-xs text-muted-foreground">No scans yet.</p>
            ) : (
              scans.map((scan) => (
                <button
                  key={scan.id}
                  type="button"
                  onClick={() => setSelectedId(scan.id)}
                  className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-4 py-3 text-left last:border-0 hover:bg-muted/40"
                >
                  <span className="truncate text-xs">{scan.summary || "Scan"}</span>
                  <StatusDot label={severityLabel(scan.severity)} tone={tone(scan.severity)} />
                </button>
              ))
            )}
          </Panel>
        </section>
        <aside className="bg-card/45 p-5 sm:p-7">
          {selected ? (
            <Outcome scan={selected} />
          ) : (
            <div className="grid h-80 place-items-center text-sm text-muted-foreground">
              Scan content to view an analysis.
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}

function Outcome({ scan }: { scan: Scan }) {
  const risk = riskStyle(scan.severity);
  const evidence = evidenceLines(scan.reasons ?? []);
  const Icon = risk.icon;
  return (
    <>
      <div className={`rounded-lg border p-4 ${risk.box}`}>
        <div className={`flex items-center gap-2 ${risk.text}`}>
          <Icon className="size-5" />
          <h2 className="font-bold">{risk.title}</h2>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{risk.detail}</p>
      </div>
      <h3 className="mt-6 text-xs font-semibold uppercase tracking-[.12em] text-muted-foreground">Key evidence</h3>
      {evidence.length === 0 ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">No separate evidence was recorded.</p>
      ) : (
        <ul className="mt-3 space-y-3 text-xs leading-5">
          {evidence.map((line) => (
            <li key={line.text} className="flex gap-2">
              <AlertTriangle className={`size-4 shrink-0 ${line.sharp ? "text-destructive" : "text-warning"}`} />
              {line.text}
            </li>
          ))}
        </ul>
      )}
      <h3 className="mt-6 text-xs font-semibold uppercase tracking-[.12em] text-muted-foreground">Reasoning summary</h3>
      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        {scan.summary || "No reasoning summary was returned."}
      </p>
      <h3 className="mt-6 text-xs font-semibold uppercase tracking-[.12em] text-muted-foreground">Full analysis</h3>
      <p className="mt-3 text-sm leading-6">{scan.rationale || "No inference was returned for this scan."}</p>
    </>
  );
}

function riskStyle(severity: string) {
  const value = severity.toLowerCase();
  if (value === "high") {
    return {
      title: "High risk",
      detail: "This content strongly resembles a phishing attempt and may be trying to steal your information.",
      box: "border-destructive/25 bg-destructive/10",
      text: "text-destructive",
      icon: ShieldAlert,
    };
  }
  if (value === "medium") {
    return {
      title: "Medium risk",
      detail: "This content has warning signs, but they do not add up to a clear scam.",
      box: "border-warning/30 bg-warning/10",
      text: "text-warning",
      icon: AlertTriangle,
    };
  }
  if (value === "low" || value === "none") {
    return {
      title: "Low risk",
      detail: "This content does not show strong signs of a phishing or scam attempt.",
      box: "border-success/25 bg-success/10",
      text: "text-success",
      icon: CheckCircle2,
    };
  }
  return {
    title: severityLabel(severity),
    detail: "This scan was stored with the result below.",
    box: "border-border bg-muted/40",
    text: "text-foreground",
    icon: ShieldAlert,
  };
}

function evidenceLines(reasons: Reason[]) {
  const lines: { text: string; sharp: boolean }[] = [];
  for (const reason of reasons) {
    if (reason.type === "llm") continue;
    if (reason.type === "heuristic" && reason.id && EVIDENCE[reason.id]) {
      lines.push({ text: EVIDENCE[reason.id], sharp: reason.id === "credential" || reason.id === "lookalike_host" });
    } else if (reason.id === "embedding_unavailable") {
      lines.push({ text: EVIDENCE.embedding_unavailable, sharp: false });
    } else if (reason.type === "embedding" && reason.label) {
      lines.push({ text: `Similar to a known ${reason.label} example.`, sharp: reason.label !== "ham" });
    } else if (reason.id === "ocr_text" && reason.detail) {
      lines.push({ text: `Text read from the image: ${clip(reason.detail)}`, sharp: false });
    } else if (reason.id === "ocr_empty") {
      lines.push({ text: EVIDENCE.ocr_empty, sharp: false });
    }
  }
  return lines;
}

function clip(value: string) {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      const comma = value.indexOf(",");
      resolve(comma >= 0 ? value.slice(comma + 1) : value);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

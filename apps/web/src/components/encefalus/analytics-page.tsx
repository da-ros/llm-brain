import { useEffect, useRef, useState } from "react";
import { Lightbulb, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice, PageHeader, Panel, PanelTitle, PremiumNotice } from "@/components/encefalus/primitives";
import { useAccount } from "@/lib/account";

type Point = { date: string; x: number; y: number };
type Pair = { r: number | null; n: number; status: string; points: Point[] };
type Day = {
  id: string;
  date: string;
  sleep_hours?: number;
  productivity_score?: number;
  meeting_hours?: number;
  focus_hours?: number;
};

const PAIRS = [
  {
    key: "sleep_productivity",
    title: "Sleep vs productivity",
    xLabel: "Sleep hours",
    yLabel: "Productivity",
  },
  {
    key: "meetings_focus",
    title: "Meetings vs focus time",
    xLabel: "Meeting hours",
    yLabel: "Focus hours",
  },
] as const;

const ACCEPT = ".csv,.xlsx,.docx,.ics,.png,.jpg,.jpeg,.webp";

function authHeaders(): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (response.status === 401 || response.status === 403) {
    return "Sign in with a premium token to see analytics.";
  }
  return fallback;
}

export function AnalyticsPage() {
  const account = useAccount();
  const [pairs, setPairs] = useState<Record<string, Pair>>({});
  const [narrative, setNarrative] = useState("");
  const [facts, setFacts] = useState<string[]>([]);
  const [days, setDays] = useState<Day[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [correlations, metrics] = await Promise.all([
        fetch("/api/analytics/correlations", { headers: authHeaders() }),
        fetch("/api/analytics/metrics", { headers: authHeaders() }),
      ]);
      if (!correlations.ok) {
        setError(await readError(correlations, "Analytics could not be loaded."));
        return;
      }
      if (!metrics.ok) {
        setError(await readError(metrics, "Analytics could not be loaded."));
        return;
      }
      const view = await correlations.json();
      const series = await metrics.json();
      setPairs(view.pairs ?? {});
      setNarrative(view.narrative ?? "");
      setFacts(view.inferred_facts ?? []);
      setDays(series.metrics ?? []);
      setError("");
    } catch {
      setError("Analytics is not reachable. Start the API router and sign in.");
    }
  }

  async function ingest(list: FileList | null) {
    const file = list?.[0];
    if (!file || busy) return;
    setBusy(true);
    setNote("");
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/api/analytics/ingest", {
        method: "POST",
        headers: authHeaders(),
        body,
      });
      if (!response.ok) {
        setError(await readError(response, "That file could not be imported."));
        setBusy(false);
        return;
      }
      const saved = await response.json();
      const count = saved.rows_upserted ?? 0;
      setNote(count === 1 ? "Saved 1 day." : `Saved ${count} days.`);
      await load();
    } catch {
      setError("Analytics is not reachable. Start the API router and sign in.");
    }
    setBusy(false);
  }

  const empty = days.length === 0 && !narrative && facts.length === 0;
  if (account?.plan === "free") return <PremiumNotice title="Analytics" />;

  return (
    <main className="min-h-svh">
      <PageHeader
        eyebrow="Life patterns"
        title="Analytics"
        description="See associations in your data without confusing correlation with causation."
        action={
          <>
            <Button variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}>
              <Upload />
              {busy ? "Importing…" : "Import data"}
            </Button>
            <input
              ref={fileRef}
              className="sr-only"
              type="file"
              accept={ACCEPT}
              disabled={busy}
              onChange={(event) => {
                void ingest(event.target.files);
                event.target.value = "";
              }}
            />
          </>
        }
      />
      <div className="p-5 sm:p-7">
        {error && (
          <div className="mb-4">
            <Notice>{error}</Notice>
          </div>
        )}
        {note && (
          <div className="mb-4">
            <Notice>{note}</Notice>
          </div>
        )}
        {empty && !error && (
          <div className="mb-4">
            <Notice>
              Import a CSV, spreadsheet, Word diary, calendar file, or photo. CSV columns can include
              date, sleep hours, productivity score, meeting hours, and focus hours.
            </Notice>
          </div>
        )}
        <div className="grid gap-4 xl:grid-cols-2">
          {PAIRS.map((spec) => (
            <PairPanel key={spec.key} spec={spec} pair={pairs[spec.key]} />
          ))}
        </div>
        <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Panel>
            <PanelTitle title="Latest reading" icon={<Lightbulb className="size-4 text-warning" />} />
            <div className="p-5">
              <p className="max-w-2xl text-sm leading-6">
                {narrative || "No reading yet. Import a file and one will be written from that upload."}
              </p>
              {facts.length > 0 && (
                <ul className="mt-4 space-y-2">
                  {facts.map((fact) => (
                    <li key={fact} className="text-xs leading-5 text-muted-foreground">
                      {fact}
                    </li>
                  ))}
                </ul>
              )}
              {narrative && (
                <div className="mt-4">
                  <Notice>
                    This reading does not establish causation. Other factors may move both measures.
                  </Notice>
                </div>
              )}
            </div>
          </Panel>
          <Panel>
            <PanelTitle title="Accepted files" />
            <div className="space-y-2 p-5 text-xs leading-5 text-muted-foreground">
              <p>CSV and Excel spreadsheets</p>
              <p>Word diaries (.docx)</p>
              <p>Calendar files (.ics)</p>
              <p>Photos (PNG, JPEG, WebP)</p>
            </div>
          </Panel>
        </div>
        <Panel className="mt-5">
          <PanelTitle title="Stored days" aside={<span className="text-xs text-muted-foreground">{days.length}</span>} />
          {days.length === 0 ? (
            <p className="p-5 text-xs text-muted-foreground">No daily measures stored yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Date</th>
                    <th className="px-4 py-2 font-medium">Sleep</th>
                    <th className="px-4 py-2 font-medium">Productivity</th>
                    <th className="px-4 py-2 font-medium">Meetings</th>
                    <th className="px-4 py-2 font-medium">Focus</th>
                  </tr>
                </thead>
                <tbody>
                  {days.map((day) => (
                    <tr key={day.id || day.date} className="border-b border-border/70">
                      <td className="px-4 py-2 font-mono">{day.date}</td>
                      <td className="px-4 py-2 font-mono">{measure(day.sleep_hours, "h")}</td>
                      <td className="px-4 py-2 font-mono">{measure(day.productivity_score)}</td>
                      <td className="px-4 py-2 font-mono">{measure(day.meeting_hours, "h")}</td>
                      <td className="px-4 py-2 font-mono">{measure(day.focus_hours, "h")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </main>
  );
}

function PairPanel({
  spec,
  pair,
}: {
  spec: (typeof PAIRS)[number];
  pair?: Pair;
}) {
  const status = pair?.status ?? "insufficient";
  const n = pair?.n ?? 0;
  const ready = status === "ok" && pair?.r != null;
  return (
    <Panel className="p-4">
      <h2 className="text-sm font-semibold">{spec.title}</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        {ready ? `${n} matched days · r = ${formatR(pair.r)}` : `Not enough matched days (${n})`}
      </p>
      <Scatter points={pair?.points ?? []} xLabel={spec.xLabel} yLabel={spec.yLabel} />
    </Panel>
  );
}

function Scatter({ points, xLabel, yLabel }: { points: Point[]; xLabel: string; yLabel: string }) {
  const [active, setActive] = useState<number | null>(null);
  if (points.length === 0) {
    return <p className="mt-8 h-44 text-xs text-muted-foreground">No matched days to plot.</p>;
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  return (
    <div className="relative mt-3 h-52 border-b border-l border-border">
      <div className="absolute inset-0 grid grid-rows-4">
        {[1, 2, 3, 4].map((row) => (
          <span key={row} className="border-t border-border/60" />
        ))}
      </div>
      {points.map((point, index) => {
        const left = 6 + ((point.x - minX) / spanX) * 86;
        const bottom = 8 + ((point.y - minY) / spanY) * 78;
        return (
          <button
            key={point.date}
            type="button"
            aria-label={`${point.date}: ${xLabel} ${point.x}, ${yLabel} ${point.y}`}
            onMouseEnter={() => setActive(index)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(index)}
            onBlur={() => setActive(null)}
            className="absolute size-2.5 rounded-full bg-primary ring-2 ring-card transition-transform hover:scale-150"
            style={{ left: `${left}%`, bottom: `${bottom}%` }}
          />
        );
      })}
      {active !== null && (
        <span className="absolute right-2 top-2 rounded bg-foreground px-2 py-1 text-[10px] text-background">
          {points[active].date}: {xLabel} {points[active].x}, {yLabel} {points[active].y}
        </span>
      )}
      <span className="absolute -bottom-6 left-0 text-[10px] text-muted-foreground">{points[0].date}</span>
      <span className="absolute -bottom-6 right-0 text-[10px] text-muted-foreground">
        {points[points.length - 1].date}
      </span>
    </div>
  );
}

function formatR(value: number | null) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function measure(value: number | undefined, suffix = "") {
  if (value == null) return "—";
  return `${value}${suffix}`;
}

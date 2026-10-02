import type { ReactNode } from "react";
import { Check, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4 border-b border-border px-5 py-5 sm:px-7">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {eyebrow}
          </p>
        )}
        <h1 className="text-xl font-bold tracking-normal text-foreground sm:text-2xl">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm leading-5 text-muted-foreground">{description}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-lg border border-border bg-card shadow-panel", className)}>
      {children}
    </section>
  );
}

export function PanelTitle({
  icon,
  title,
  aside,
}: {
  icon?: ReactNode;
  title: string;
  aside?: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-4 py-3">
      <div className="flex min-w-0 items-center gap-2 text-sm font-semibold">
        {icon}
        <span className="truncate">{title}</span>
      </div>
      {aside}
    </div>
  );
}

export function StatusDot({
  tone = "good",
  label,
}: {
  tone?: "good" | "warn" | "bad" | "neutral";
  label: string;
}) {
  const tones = {
    good: "bg-success",
    warn: "bg-warning",
    bad: "bg-destructive",
    neutral: "bg-muted-foreground",
  };
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted-foreground">
      <span className={cn("size-1.5 rounded-full", tones[tone])} />
      {label}
    </span>
  );
}

export function Metric({
  label,
  value,
  note,
  icon,
}: {
  label: string;
  value: string;
  note: string;
  icon?: ReactNode;
}) {
  return (
    <Panel className="min-h-28 p-4">
      <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
        <span>{label}</span>
        {icon}
      </div>
      <p className="mt-3 font-mono text-2xl font-semibold text-foreground">{value}</p>
      <p className="mt-1 text-[11px] text-muted-foreground">{note}</p>
    </Panel>
  );
}

export function EvidenceList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item} className="flex gap-2 text-xs leading-5 text-muted-foreground">
          <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
          {item}
        </li>
      ))}
    </ul>
  );
}

export function PremiumNotice({ title }: { title: string }) {
  return (
    <main className="min-h-svh">
      <PageHeader
        eyebrow="Premium plan"
        title={title}
        description="The Free plan includes Brain chat and your chat list. This screen is on the Premium plan."
      />
      <div className="p-5 sm:p-7">
        <Notice>You can switch to Premium in Settings.</Notice>
      </div>
    </main>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-2 rounded-md border border-border bg-muted/45 p-3 text-xs leading-5 text-muted-foreground">
      <Info className="mt-0.5 size-3.5 shrink-0" />
      {children}
    </div>
  );
}

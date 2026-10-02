import { Link, useRouterState } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import {
  BarChart3,
  BrainCog,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
  Database,
  Scale,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { initials, planLabel, useAccount } from "@/lib/account";
import { cn } from "@/lib/utils";

export const primaryItems = [
  { label: "Brain", to: "/brain", icon: BrainCog },
  { label: "Memory", to: "/memory", icon: Database },
  { label: "Decisions", to: "/decisions", icon: Scale },
  { label: "Analytics", to: "/analytics", icon: BarChart3 },
  { label: "Shield", to: "/shield", icon: ShieldCheck },
  { label: "Learning", to: "/learning", icon: Sparkles },
] as const;

function BrandMark({
  compact = false,
  onNavigate,
}: {
  compact?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      to="/"
      onClick={onNavigate}
      aria-label="Encefalus home"
      className="flex min-w-0 items-center gap-2.5 rounded-md"
    >
      <img src="/encefalus-mark.png" alt="" className="size-8 shrink-0" />
      {!compact && (
        <span className="truncate text-[15px] font-bold text-foreground">Encefalus</span>
      )}
    </Link>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const account = useAccount();
  const path = useRouterState({ select: (state) => state.location.pathname });
  return (
    <>
      <div className="px-3 py-4">
        <BrandMark onNavigate={onNavigate} />
      </div>
      <nav className="flex flex-1 flex-col px-2" aria-label="Main navigation">
        <div className="space-y-1">
          {primaryItems.map((item) => {
            const active = path === item.to;
            return (
              <Link
                key={item.label}
                to={item.to}
                onClick={onNavigate}
                className={cn(
                  "flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <item.icon className="size-4 shrink-0" strokeWidth={1.7} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
        <div className="my-4 border-t border-sidebar-border" />
        <Link
          to="/settings"
          onClick={onNavigate}
          className={cn(
            "flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
            path === "/settings"
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
          )}
        >
          <Settings className="size-4" strokeWidth={1.7} />
          <span>Settings</span>
        </Link>
      </nav>
      <div className="space-y-3 p-3">
        <div className="flex h-9 items-center gap-2 rounded-md border border-sidebar-border bg-background px-2.5 text-muted-foreground">
          <Search className="size-3.5" />
          <span className="text-xs">Search anything…</span>
          <kbd className="ml-auto text-[10px]">⌘K</kbd>
        </div>
        <Link
          to="/settings"
          onClick={onNavigate}
          className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-2 rounded-md px-1 py-1 hover:bg-sidebar-accent/60"
        >
          <span className="grid size-7 place-items-center rounded-full bg-secondary text-[10px] font-bold text-secondary-foreground">
            {account ? initials(account.name) : "?"}
          </span>
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold">{account ? account.name : "Sign in"}</p>
            <p className="truncate text-[10px] text-muted-foreground">
              {account ? planLabel(account.plan) : "Create an account"}
            </p>
          </div>
        </Link>
      </div>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="min-h-svh bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[220px] flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <Navigation />
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-foreground/20"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative flex h-full w-[280px] flex-col border-r border-sidebar-border bg-sidebar shadow-xl">
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-2"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X />
            </Button>
            <Navigation onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
      <div className="lg:pl-[220px]">
        <header className="sticky top-0 z-20 grid h-14 grid-cols-[auto_minmax(0,1fr)_auto] items-center border-b border-border bg-background/95 px-4 backdrop-blur lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu />
          </Button>
          <div className="justify-self-center">
            <BrandMark />
          </div>
          <span className="size-9" />
        </header>
        {children}
      </div>
    </div>
  );
}

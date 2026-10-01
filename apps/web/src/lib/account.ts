import { useEffect, useState } from "react";

export type Account = {
  id: string;
  name: string;
  email: string;
  plan: "free" | "premium";
};

const ACCOUNT_KEY = "encefalus_account";

export function readAccount(): Account | null {
  try {
    const raw = sessionStorage.getItem(ACCOUNT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Account;
    if (!parsed?.name || !parsed?.email) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveSession(token: string, user: Account) {
  sessionStorage.setItem("access_token", token);
  sessionStorage.setItem(ACCOUNT_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("encefalus-auth"));
}

export function clearSession() {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem(ACCOUNT_KEY);
  window.dispatchEvent(new Event("encefalus-auth"));
}

export function authHeaders(json = false): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export function planLabel(plan: string): string {
  return plan === "premium" ? "Premium plan" : "Free plan";
}

export function useAccount() {
  const [account, setAccount] = useState<Account | null>(() =>
    typeof window === "undefined" ? null : readAccount(),
  );
  useEffect(() => {
    const sync = () => setAccount(readAccount());
    sync();
    window.addEventListener("encefalus-auth", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("encefalus-auth", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return account;
}

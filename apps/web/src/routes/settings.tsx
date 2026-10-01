import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/encefalus/settings-page";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — Encefalus" },
      {
        name: "description",
        content: "Sign in, choose a free or premium plan, and manage your Brain.",
      },
      { property: "og:title", content: "Settings — Encefalus" },
      { property: "og:description", content: "Account, service health, and document memory." },
    ],
  }),
  component: SettingsPage,
});

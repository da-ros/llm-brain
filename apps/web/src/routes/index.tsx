import { createFileRoute } from "@tanstack/react-router";
import { HomePage } from "@/components/encefalus/home-page";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Home — Encefalus" },
      { name: "description", content: "Your AI-augmented brain for clearer thinking, better decisions, and a more capable you." },
      { property: "og:title", content: "Home — Encefalus" },
      { property: "og:description", content: "Everything your Encefalus Brain can do, in one place." },
    ],
  }),
  component: HomePage,
});

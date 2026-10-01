import { createFileRoute } from "@tanstack/react-router";
import { MemoryPage } from "@/components/encefalus/memory-page";

export const Route = createFileRoute("/memory")({
  head: () => ({
    meta: [
      { title: "Memory — Encefalus" },
      { name: "description", content: "Search and manage the documents, images, and video in your personal memory." },
      { property: "og:title", content: "Memory — Encefalus" },
      { property: "og:description", content: "Your searchable personal memory repository." },
    ],
  }),
  component: MemoryPage,
});

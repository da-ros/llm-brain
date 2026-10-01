import { createFileRoute } from "@tanstack/react-router";
import { AnalyticsPage } from "@/components/encefalus/analytics-page";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [
      { title: "Analytics — Encefalus" },
      {
        name: "description",
        content: "Associations from imported days, with the latest reading and stored measures.",
      },
      { property: "og:title", content: "Analytics — Encefalus" },
      { property: "og:description", content: "Personal life patterns, interpreted carefully." },
    ],
  }),
  component: AnalyticsPage,
});

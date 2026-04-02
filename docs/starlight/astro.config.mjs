import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import rehypeMermaid from "rehype-mermaid";

export default defineConfig({
  site: "https://asong65535.github.io",
  base: "/lead-scoring",
  markdown: {
    rehypePlugins: [rehypeMermaid],
  },
  integrations: [
    starlight({
      title: "Lead Scoring",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/asong65535/lead-scoring",
        },
      ],
      sidebar: [
        { label: "Home", link: "/" },
        {
          label: "System",
          items: [
            { label: "Architecture", slug: "architecture" },
            { label: "Database", slug: "database" },
            { label: "Configuration", slug: "configuration" },
          ],
        },
        {
          label: "Pipeline",
          items: [
            { label: "Data Pipeline", slug: "data-pipeline" },
            { label: "ML Model", slug: "ml-model" },
          ],
        },
        {
          label: "Integration",
          items: [
            { label: "API Reference", slug: "api" },
            { label: "CRM Integration", slug: "crm-integration" },
          ],
        },
        {
          label: "Operations",
          items: [
            { label: "Deployment", slug: "deployment" },
            { label: "Runbook", slug: "runbook" },
          ],
        },
      ],
    }),
  ],
});

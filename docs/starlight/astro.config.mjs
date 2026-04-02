import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import rehypeMermaid from "rehype-mermaid";

export default defineConfig({
  site: "https://asong65535.github.io",
  base: "/lead-scoring",
  markdown: {
    syntaxHighlight: {
      excludeLangs: ["mermaid"]
    },
    rehypePlugins: [[rehypeMermaid, { strategy: "img-svg", dark: true}]]
  },
  integrations: [
    starlight({
      title: "Lead Scoring",
      head: [
        {
          tag: "script",
          content: `
            (function() {
              function syncMermaidTheme() {
                const isDark = document.documentElement.dataset.theme === 'dark';
                document.querySelectorAll('picture').forEach(picture => {
                  const darkSource = picture.querySelector('source[media="(prefers-color-scheme: dark)"]');
                  const img = picture.querySelector('img');
                  if (!darkSource || !img) return;
                  if (!img.dataset.lightSrc) {
                    img.dataset.lightSrc = img.src;
                    img.dataset.darkSrc = darkSource.srcset;
                  }
                  img.src = isDark ? img.dataset.darkSrc : img.dataset.lightSrc;
                });
              }
              if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', syncMermaidTheme);
              } else {
                syncMermaidTheme();
              }
              new MutationObserver(() => syncMermaidTheme()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
            })();
          `,
        },
      ],
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

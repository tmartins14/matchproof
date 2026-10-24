import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
  { ignores: [".next/**", "next-env.d.ts", "src/contracts/types.ts", "test-results/**", "playwright-report/**"] },
  {
    rules: {
      "no-restricted-exports": [
        "error",
        { restrictDefaultExports: { direct: true, named: true, defaultFrom: true, namedFrom: true, namespaceFrom: true } },
      ],
    },
  },
  {
    // Next.js requires default exports for pages, layouts and config.
    files: ["src/app/**/{page,layout}.tsx", "next.config.ts", "eslint.config.mjs", "playwright.config.ts", "vitest.config.mts"],
    rules: { "no-restricted-exports": "off" },
  },
];

export default config;

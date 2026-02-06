import "dotenv/config";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
    seed: "bun ./prisma/seed.ts",
  },
  datasource: {
    // Use the direct (non-pooled) connection for CLI commands (migrations, introspection)
    url: process.env["POSTGRES_URL_NON_POOLING"],
  },
});

# Database Setup

This project uses **PostgreSQL** hosted on **Vercel Postgres** (powered by Neon) with **Prisma 7** as the ORM.

## Prerequisites

- A Vercel account with a project linked to this repo
- Node.js installed locally

## 1. Create the Database

1. Go to your [Vercel project dashboard](https://vercel.com/dashboard)
2. Navigate to **Storage** tab
3. Click **Create Database** → select **Postgres (Neon)**
4. Link it to your project

## 2. Pull Environment Variables

```bash
cd application
npx vercel env pull .env
```

This populates your `.env` with the connection strings Vercel generated. The key variables are:

| Variable | Purpose |
|----------|---------|
| `POSTGRES_PRISMA_URL` | Pooled connection — used at runtime by Prisma Client (via Neon adapter) |
| `POSTGRES_URL_NON_POOLING` | Direct connection — used by Prisma CLI for migrations |

## 3. Generate Prisma Client

```bash
npx prisma generate
```

This generates the typed client into `lib/generated/prisma/`.

## 4. Run Migrations

```bash
npx prisma migrate dev --name init
```

This creates the tables in your database based on `prisma/schema.prisma`.

For production deployments, use:

```bash
npx prisma migrate deploy
```

## 5. Seed the Database

```bash
npx prisma db seed
```

This reads `data/videos.jsonl` and upserts all channels and videos into the database. Safe to run multiple times.

## 6. Verify (Optional)

```bash
npx prisma studio
```

Opens a web UI at `http://localhost:5555` where you can browse your data.

## Common Commands

```bash
# Generate client after schema changes
npx prisma generate

# Create a new migration
npx prisma migrate dev --name <description>

# Deploy migrations (CI/production)
npx prisma migrate deploy

# Reset database (drops all data, re-runs migrations + seed)
npx prisma migrate reset

# Open Prisma Studio
npx prisma studio

# Seed the database
npx prisma db seed
```

## Architecture

- **`prisma/schema.prisma`** — Database schema (models: User, Account, Session, VerificationToken, Video, Channel, Review)
- **`prisma.config.ts`** — Prisma CLI config, points to `POSTGRES_URL_NON_POOLING` for migrations
- **`lib/prisma.ts`** — Prisma Client singleton with Neon serverless adapter
- **`prisma/seed.ts`** — Seed script to load `data/videos.jsonl` into the database

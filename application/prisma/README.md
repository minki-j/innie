# Prisma Migrations

## Prerequisites

- PostgreSQL connection string set in `POSTGRES_PRISMA_URL` (see `.env`)
- All commands should be run from the `application/` directory

## Common Commands

### Create a migration after editing `schema.prisma`

```bash
npx prisma migrate dev --name <migration_name>
```

This will:

1. Generate a new SQL migration file in `prisma/migrations/`
2. Apply the migration to your development database
3. Re-generate the Prisma client

Use a short, descriptive snake_case name (e.g. `add_topic_to_review`, `add_training_run_and_transcript`).

### Apply pending migrations (no new changes)

```bash
npx prisma migrate dev
```

### Reset the database (destructive)

```bash
npx prisma migrate reset
```

This drops the database, re-applies all migrations from scratch, and runs the seed script.

### Check migration status

```bash
npx prisma migrate status
```

### Deploy migrations to production / CI

```bash
npx prisma migrate deploy
```

Unlike `migrate dev`, this only applies pending migrations and never creates new ones. Use this in production environments and CI/CD pipelines.

## Generating the Prisma Client

The client is output to `lib/generated/prisma/` (configured in `schema.prisma`). It is automatically regenerated when you run `migrate dev`, but you can also regenerate it manually:

```bash
npx prisma generate
```

## Seeding

The seed script is defined in `package.json` under `prisma.seed` and runs via:

```bash
npx prisma db seed
```

It is also executed automatically on `migrate reset`.

## Tips

- **Never** edit or delete existing migration SQL files that have already been applied. If you need to undo a change, create a new migration instead.
- If your local database gets out of sync, `migrate reset` is the fastest way to start fresh.
- Use `npx prisma studio` to visually browse and edit data during development.

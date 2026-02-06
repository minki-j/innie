# Topics Feature

## Overview

Topics let users organize and filter YouTube videos by subject areas they want to track. Each user can create multiple topics, define what qualifies content for a topic, and configure how new videos are discovered.

## Data Model

```
User
 └── Topic (name, description)
      ├── Criterion      — conditions that define topic relevance
      ├── GoldStandard   — reference videos (positive & negative examples)
      ├── TopicKeyword   — YouTube search terms for discovery
      ├── TopicCreator   — YouTube channels to scrape
      └── Video[]        — many-to-many: videos assigned to this topic
```

### Criterion

Each criterion is a natural-language condition with two attributes:

- **Include / Exclude** — whether matching this condition means a video belongs or doesn't belong.
- **Must Have / Nice to Have** — priority level.

Example: *"The content mentions MCP integration in enterprise: Include, Must Have"*

### Gold Standards

Reference videos split into two categories:

- **Positive** — exemplary videos that match the topic well.
- **Negative** — videos that should *not* match despite surface-level similarity.

Each entry stores a YouTube URL, an optional cached title, and an optional note.

### Keywords

Simple text strings used as YouTube search queries for automated video discovery.

### Creators

YouTube channels the user wants to monitor. Each entry includes:

- Channel name and/or URL
- **Scrape period** — how far back to look for videos (1–12 months)

## UI

### Home Page (`/`)

- A **topic filter bar** appears above the video grid when the user has topics.
- "All Topics" is selected by default; users can multi-select topics to filter.
- Each video card displays **topic badges** showing which topics it belongs to.

### Watch Page (`/watch/[videoId]`)

- Topic badges appear below the video title.

### Settings (`/settings/topics`)

- Accessible via the **gear icon** in the navbar (visible when logged in).
- **List view** — shows all topics with counts (videos, criteria, keywords, creators). Users can add or delete topics here.
- **Detail view** (`/settings/topics/[topicId]`) — five collapsible sections:
  1. **Overview** — edit name and description
  2. **Criteria** — add/edit/remove criteria with include/exclude and level toggles
  3. **Gold Standards** — manage positive and negative reference videos
  4. **Keywords** — tag-style keyword input
  5. **YouTube Creators** — manage channels with scrape period selector

## API

All routes require authentication and enforce topic ownership.

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/topics` | List user's topics |
| POST | `/api/topics` | Create topic |
| GET | `/api/topics/[id]` | Get topic with all relations |
| PUT | `/api/topics/[id]` | Update topic name/description |
| DELETE | `/api/topics/[id]` | Delete topic and all children |
| POST/PUT/DELETE | `/api/topics/[id]/criteria` | Manage criteria |
| POST/PUT/DELETE | `/api/topics/[id]/gold-standards` | Manage gold standards |
| POST/DELETE | `/api/topics/[id]/keywords` | Manage keywords |
| POST/PUT/DELETE | `/api/topics/[id]/creators` | Manage creators |

## Key Files

- `prisma/schema.prisma` — Topic, Criterion, GoldStandard, TopicKeyword, TopicCreator models
- `lib/videos.ts` — video queries with topic includes and optional filtering
- `lib/topics.ts` — helper to fetch current user's topics
- `components/topic/` — all topic UI components (filter, badges, editors)
- `app/api/topics/` — API route handlers
- `app/(main)/settings/topics/` — settings pages

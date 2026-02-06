import { PrismaClient } from "../lib/generated/prisma/client";
import { PrismaNeon } from "@prisma/adapter-neon";
import "dotenv/config";
import fs from "fs";
import path from "path";

const adapter = new PrismaNeon({
  connectionString: process.env.POSTGRES_PRISMA_URL!,
});
const prisma = new PrismaClient({ adapter });

interface VideoManifestEntry {
  video_id: string;
  title: string;
  description: string;
  channel: string;
  channel_id: string;
  upload_date: string; // "YYYYMMDD"
  view_count: number;
  like_count: number;
  duration_seconds: number;
  tags: string[];
  [key: string]: unknown;
}

function parseUploadDate(dateStr: string): Date {
  const year = dateStr.slice(0, 4);
  const month = dateStr.slice(4, 6);
  const day = dateStr.slice(6, 8);
  return new Date(`${year}-${month}-${day}T00:00:00Z`);
}

async function main() {
  const filePath = path.join(process.cwd(), "data", "videos.jsonl");
  const content = fs.readFileSync(filePath, "utf-8");
  const lines = content.trim().split("\n");

  // Collect unique channels first
  const channelMap = new Map<string, { id: string; title: string }>();

  const entries: VideoManifestEntry[] = lines
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as VideoManifestEntry);

  for (const entry of entries) {
    if (!channelMap.has(entry.channel_id)) {
      channelMap.set(entry.channel_id, {
        id: entry.channel_id,
        title: entry.channel,
      });
    }
  }

  // Upsert channels
  console.log(`Seeding ${channelMap.size} channels...`);
  for (const channel of channelMap.values()) {
    await prisma.channel.upsert({
      where: { id: channel.id },
      update: { title: channel.title },
      create: {
        id: channel.id,
        title: channel.title,
      },
    });
  }

  // Upsert videos
  console.log(`Seeding ${entries.length} videos...`);
  for (const entry of entries) {
    await prisma.video.upsert({
      where: { id: entry.video_id },
      update: {
        title: entry.title,
        description: entry.description,
        channelTitle: entry.channel,
        channelId: entry.channel_id,
        publishedAt: parseUploadDate(entry.upload_date),
        viewCount: entry.view_count,
        likeCount: entry.like_count,
        durationSeconds: entry.duration_seconds,
        tags: entry.tags ?? [],
      },
      create: {
        id: entry.video_id,
        title: entry.title,
        description: entry.description,
        channelTitle: entry.channel,
        channelId: entry.channel_id,
        publishedAt: parseUploadDate(entry.upload_date),
        viewCount: entry.view_count,
        likeCount: entry.like_count,
        durationSeconds: entry.duration_seconds,
        tags: entry.tags ?? [],
      },
    });
  }

  console.log("Seeding complete!");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });

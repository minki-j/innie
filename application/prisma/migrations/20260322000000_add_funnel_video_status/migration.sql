-- CreateEnum
CREATE TYPE "FunnelVideoStatus" AS ENUM ('PENDING', 'PROCESSING', 'PENDING_RETRY', 'FAILED', 'COMPLETED');

-- CreateTable (before dropping _FunnelToVideo so we can migrate data)
CREATE TABLE "FunnelVideo" (
    "funnelId" TEXT NOT NULL,
    "videoId" TEXT NOT NULL,
    "status" "FunnelVideoStatus" NOT NULL DEFAULT 'PENDING',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FunnelVideo_pkey" PRIMARY KEY ("funnelId","videoId")
);

-- CreateIndex
CREATE INDEX "FunnelVideo_funnelId_updatedAt_idx" ON "FunnelVideo"("funnelId", "updatedAt");

-- CreateIndex
CREATE INDEX "FunnelVideo_videoId_idx" ON "FunnelVideo"("videoId");

-- AddForeignKey
ALTER TABLE "FunnelVideo" ADD CONSTRAINT "FunnelVideo_funnelId_fkey" FOREIGN KEY ("funnelId") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FunnelVideo" ADD CONSTRAINT "FunnelVideo_videoId_fkey" FOREIGN KEY ("videoId") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Migrate existing data: copy all rows from implicit join table, marking as COMPLETED
INSERT INTO "FunnelVideo" ("funnelId", "videoId", "status", "createdAt", "updatedAt")
SELECT "A", "B", 'COMPLETED'::"FunnelVideoStatus", CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM "_FunnelToVideo"
ON CONFLICT ("funnelId", "videoId") DO NOTHING;

-- DropForeignKey
ALTER TABLE "_FunnelToVideo" DROP CONSTRAINT "_FunnelToVideo_A_fkey";

-- DropForeignKey
ALTER TABLE "_FunnelToVideo" DROP CONSTRAINT "_FunnelToVideo_B_fkey";

-- DropTable
DROP TABLE "_FunnelToVideo";

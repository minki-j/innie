-- DropIndex
DROP INDEX "IdeaGraph_userId_videoId_key";

-- CreateIndex
CREATE INDEX "IdeaGraph_userId_videoId_createdAt_idx" ON "IdeaGraph"("userId", "videoId", "createdAt");

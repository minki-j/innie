-- DropIndex
DROP INDEX "Review_userId_videoId_key";

-- AlterTable
ALTER TABLE "Review" ADD COLUMN     "topicId" TEXT;

-- CreateIndex
CREATE INDEX "Review_topicId_idx" ON "Review"("topicId");

-- CreateIndex
CREATE UNIQUE INDEX "Review_userId_videoId_topicId_key" ON "Review"("userId", "videoId", "topicId");

-- AddForeignKey
ALTER TABLE "Review" ADD CONSTRAINT "Review_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

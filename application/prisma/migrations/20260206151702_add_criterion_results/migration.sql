-- CreateEnum
CREATE TYPE "CriterionResultValue" AS ENUM ('PASS', 'FAIL', 'CANNOT_TELL');

-- AlterTable
ALTER TABLE "Topic" ADD COLUMN     "active" BOOLEAN NOT NULL DEFAULT true;

-- CreateTable
CREATE TABLE "CriterionResult" (
    "id" TEXT NOT NULL,
    "videoId" TEXT NOT NULL,
    "criterionId" TEXT NOT NULL,
    "result" "CriterionResultValue" NOT NULL,
    "explanation" TEXT,
    "modelUsed" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CriterionResult_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "CriterionResult_videoId_idx" ON "CriterionResult"("videoId");

-- CreateIndex
CREATE INDEX "CriterionResult_criterionId_idx" ON "CriterionResult"("criterionId");

-- CreateIndex
CREATE UNIQUE INDEX "CriterionResult_videoId_criterionId_key" ON "CriterionResult"("videoId", "criterionId");

-- AddForeignKey
ALTER TABLE "CriterionResult" ADD CONSTRAINT "CriterionResult_videoId_fkey" FOREIGN KEY ("videoId") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CriterionResult" ADD CONSTRAINT "CriterionResult_criterionId_fkey" FOREIGN KEY ("criterionId") REFERENCES "Criterion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

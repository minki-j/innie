-- AlterTable
ALTER TABLE "Topic" ADD COLUMN     "lastPipelineRunAt" TIMESTAMP(3),
ADD COLUMN     "pipelineIntervalHours" INTEGER NOT NULL DEFAULT 6;

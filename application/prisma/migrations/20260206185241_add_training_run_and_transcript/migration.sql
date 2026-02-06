-- CreateEnum
CREATE TYPE "TrainingStatus" AS ENUM ('PENDING', 'TRAINING', 'COMPLETED', 'FAILED');

-- CreateEnum
CREATE TYPE "TrainingMethod" AS ENUM ('SFT', 'RLVR');

-- AlterTable
ALTER TABLE "Video" ADD COLUMN     "transcript" TEXT;

-- CreateTable
CREATE TABLE "TrainingRun" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "topicId" TEXT NOT NULL,
    "status" "TrainingStatus" NOT NULL DEFAULT 'PENDING',
    "method" "TrainingMethod" NOT NULL,
    "modelName" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "checkpointPath" TEXT,
    "baseModel" TEXT NOT NULL DEFAULT 'meta-llama/Llama-3.1-8B-Instruct',
    "config" JSONB,
    "metrics" JSONB,
    "datasetSize" INTEGER,
    "webhookUrl" TEXT,
    "error" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "TrainingRun_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "TrainingRun_modelName_key" ON "TrainingRun"("modelName");

-- CreateIndex
CREATE INDEX "TrainingRun_userId_topicId_idx" ON "TrainingRun"("userId", "topicId");

-- CreateIndex
CREATE INDEX "TrainingRun_topicId_method_isActive_idx" ON "TrainingRun"("topicId", "method", "isActive");

-- AddForeignKey
ALTER TABLE "TrainingRun" ADD CONSTRAINT "TrainingRun_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TrainingRun" ADD CONSTRAINT "TrainingRun_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

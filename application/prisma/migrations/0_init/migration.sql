-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "ClassNodeResultValue" AS ENUM ('PASS', 'FAIL', 'CANNOT_TELL');

-- CreateEnum
CREATE TYPE "TrainingStatus" AS ENUM ('PENDING', 'TRAINING', 'COMPLETED', 'FAILED', 'CANCELLED');

-- CreateEnum
CREATE TYPE "TrainingMethod" AS ENUM ('SFT', 'RLVR');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "name" TEXT,
    "email" TEXT,
    "emailVerified" TIMESTAMP(3),
    "image" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Account" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    "refresh_token" TEXT,
    "access_token" TEXT,
    "expires_at" INTEGER,
    "token_type" TEXT,
    "scope" TEXT,
    "id_token" TEXT,
    "session_state" TEXT,

    CONSTRAINT "Account_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "sessionToken" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "expires" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VerificationToken" (
    "identifier" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "expires" TIMESTAMP(3) NOT NULL
);

-- CreateTable
CREATE TABLE "Video" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "channelTitle" TEXT NOT NULL,
    "channelId" TEXT NOT NULL,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "viewCount" BIGINT NOT NULL DEFAULT 0,
    "likeCount" BIGINT NOT NULL DEFAULT 0,
    "commentCount" BIGINT NOT NULL DEFAULT 0,
    "durationSeconds" INTEGER NOT NULL,
    "definition" TEXT NOT NULL DEFAULT 'hd',
    "caption" TEXT NOT NULL DEFAULT 'false',
    "tags" TEXT[],
    "thumbnailDefault" TEXT,
    "thumbnailMedium" TEXT,
    "thumbnailHigh" TEXT,
    "transcript" TEXT,
    "summary" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Video_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Channel" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "customUrl" TEXT,
    "thumbnailUrl" TEXT,
    "subscriberCount" BIGINT NOT NULL DEFAULT 0,
    "videoCount" BIGINT NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Channel_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Review" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "videoId" TEXT NOT NULL,
    "funnelId" TEXT,
    "rating" INTEGER NOT NULL,
    "content" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Review_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Funnel" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "userId" TEXT NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "pipelineIntervalHours" INTEGER NOT NULL DEFAULT 6,
    "lastPipelineRunAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Funnel_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ClassNode" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL DEFAULT '',
    "description" TEXT,
    "parentClassNodeId" TEXT,
    "funnelId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ClassNode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "GoldStandard" (
    "id" TEXT NOT NULL,
    "classNodeId" TEXT NOT NULL,
    "videoUrl" TEXT NOT NULL,
    "title" TEXT,
    "isPositive" BOOLEAN NOT NULL DEFAULT true,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "GoldStandard_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FunnelKeyword" (
    "id" TEXT NOT NULL,
    "funnelId" TEXT NOT NULL,
    "keyword" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "FunnelKeyword_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FunnelCreator" (
    "id" TEXT NOT NULL,
    "funnelId" TEXT NOT NULL,
    "channelId" TEXT,
    "channelUrl" TEXT,
    "channelName" TEXT,
    "scrapeMonthsBack" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "FunnelCreator_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LLM" (
    "id" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LLM_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ClassNodeResult" (
    "id" TEXT NOT NULL,
    "videoId" TEXT NOT NULL,
    "classNodeId" TEXT NOT NULL,
    "result" "ClassNodeResultValue" NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "explanation" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ClassNodeResult_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ClassNodeModelVerdict" (
    "id" TEXT NOT NULL,
    "videoId" TEXT NOT NULL,
    "classNodeId" TEXT NOT NULL,
    "classNodeResultId" TEXT NOT NULL,
    "llmId" TEXT NOT NULL,
    "rationale" TEXT NOT NULL,
    "verdict" BOOLEAN NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ClassNodeModelVerdict_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TrainingRun" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "funnelId" TEXT NOT NULL,
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

-- CreateTable
CREATE TABLE "_FunnelToVideo" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL,

    CONSTRAINT "_FunnelToVideo_AB_pkey" PRIMARY KEY ("A","B")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "Account_provider_providerAccountId_key" ON "Account"("provider", "providerAccountId");

-- CreateIndex
CREATE UNIQUE INDEX "Session_sessionToken_key" ON "Session"("sessionToken");

-- CreateIndex
CREATE UNIQUE INDEX "VerificationToken_token_key" ON "VerificationToken"("token");

-- CreateIndex
CREATE UNIQUE INDEX "VerificationToken_identifier_token_key" ON "VerificationToken"("identifier", "token");

-- CreateIndex
CREATE INDEX "Video_channelId_idx" ON "Video"("channelId");

-- CreateIndex
CREATE INDEX "Video_publishedAt_idx" ON "Video"("publishedAt");

-- CreateIndex
CREATE INDEX "Review_videoId_idx" ON "Review"("videoId");

-- CreateIndex
CREATE INDEX "Review_funnelId_idx" ON "Review"("funnelId");

-- CreateIndex
CREATE UNIQUE INDEX "Review_userId_videoId_funnelId_key" ON "Review"("userId", "videoId", "funnelId");

-- CreateIndex
CREATE INDEX "Funnel_userId_idx" ON "Funnel"("userId");

-- CreateIndex
CREATE INDEX "ClassNode_funnelId_idx" ON "ClassNode"("funnelId");

-- CreateIndex
CREATE INDEX "GoldStandard_classNodeId_idx" ON "GoldStandard"("classNodeId");

-- CreateIndex
CREATE INDEX "FunnelKeyword_funnelId_idx" ON "FunnelKeyword"("funnelId");

-- CreateIndex
CREATE INDEX "FunnelCreator_funnelId_idx" ON "FunnelCreator"("funnelId");

-- CreateIndex
CREATE INDEX "ClassNodeResult_videoId_idx" ON "ClassNodeResult"("videoId");

-- CreateIndex
CREATE INDEX "ClassNodeResult_classNodeId_idx" ON "ClassNodeResult"("classNodeId");

-- CreateIndex
CREATE UNIQUE INDEX "ClassNodeResult_videoId_classNodeId_key" ON "ClassNodeResult"("videoId", "classNodeId");

-- CreateIndex
CREATE INDEX "ClassNodeModelVerdict_videoId_idx" ON "ClassNodeModelVerdict"("videoId");

-- CreateIndex
CREATE INDEX "ClassNodeModelVerdict_classNodeId_idx" ON "ClassNodeModelVerdict"("classNodeId");

-- CreateIndex
CREATE INDEX "ClassNodeModelVerdict_classNodeResultId_idx" ON "ClassNodeModelVerdict"("classNodeResultId");

-- CreateIndex
CREATE INDEX "ClassNodeModelVerdict_llmId_idx" ON "ClassNodeModelVerdict"("llmId");

-- CreateIndex
CREATE UNIQUE INDEX "ClassNodeModelVerdict_videoId_classNodeId_llmId_key" ON "ClassNodeModelVerdict"("videoId", "classNodeId", "llmId");

-- CreateIndex
CREATE UNIQUE INDEX "TrainingRun_modelName_key" ON "TrainingRun"("modelName");

-- CreateIndex
CREATE INDEX "TrainingRun_userId_funnelId_idx" ON "TrainingRun"("userId", "funnelId");

-- CreateIndex
CREATE INDEX "TrainingRun_funnelId_method_isActive_idx" ON "TrainingRun"("funnelId", "method", "isActive");

-- CreateIndex
CREATE INDEX "_FunnelToVideo_B_index" ON "_FunnelToVideo"("B");

-- AddForeignKey
ALTER TABLE "Account" ADD CONSTRAINT "Account_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Video" ADD CONSTRAINT "Video_channelId_fkey" FOREIGN KEY ("channelId") REFERENCES "Channel"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Review" ADD CONSTRAINT "Review_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Review" ADD CONSTRAINT "Review_videoId_fkey" FOREIGN KEY ("videoId") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Review" ADD CONSTRAINT "Review_funnelId_fkey" FOREIGN KEY ("funnelId") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Funnel" ADD CONSTRAINT "Funnel_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNode" ADD CONSTRAINT "ClassNode_parentClassNodeId_fkey" FOREIGN KEY ("parentClassNodeId") REFERENCES "ClassNode"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNode" ADD CONSTRAINT "ClassNode_funnelId_fkey" FOREIGN KEY ("funnelId") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "GoldStandard" ADD CONSTRAINT "GoldStandard_classNodeId_fkey" FOREIGN KEY ("classNodeId") REFERENCES "ClassNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FunnelKeyword" ADD CONSTRAINT "FunnelKeyword_funnelId_fkey" FOREIGN KEY ("funnelId") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FunnelCreator" ADD CONSTRAINT "FunnelCreator_funnelId_fkey" FOREIGN KEY ("funnelId") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNodeResult" ADD CONSTRAINT "ClassNodeResult_videoId_fkey" FOREIGN KEY ("videoId") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNodeResult" ADD CONSTRAINT "ClassNodeResult_classNodeId_fkey" FOREIGN KEY ("classNodeId") REFERENCES "ClassNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNodeModelVerdict" ADD CONSTRAINT "ClassNodeModelVerdict_videoId_fkey" FOREIGN KEY ("videoId") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNodeModelVerdict" ADD CONSTRAINT "ClassNodeModelVerdict_classNodeId_fkey" FOREIGN KEY ("classNodeId") REFERENCES "ClassNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNodeModelVerdict" ADD CONSTRAINT "ClassNodeModelVerdict_classNodeResultId_fkey" FOREIGN KEY ("classNodeResultId") REFERENCES "ClassNodeResult"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ClassNodeModelVerdict" ADD CONSTRAINT "ClassNodeModelVerdict_llmId_fkey" FOREIGN KEY ("llmId") REFERENCES "LLM"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TrainingRun" ADD CONSTRAINT "TrainingRun_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TrainingRun" ADD CONSTRAINT "TrainingRun_funnelId_fkey" FOREIGN KEY ("funnelId") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_FunnelToVideo" ADD CONSTRAINT "_FunnelToVideo_A_fkey" FOREIGN KEY ("A") REFERENCES "Funnel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_FunnelToVideo" ADD CONSTRAINT "_FunnelToVideo_B_fkey" FOREIGN KEY ("B") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;


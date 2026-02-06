-- CreateTable
CREATE TABLE "Topic" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "userId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Topic_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Criterion" (
    "id" TEXT NOT NULL,
    "topicId" TEXT NOT NULL,
    "condition" TEXT NOT NULL,
    "include" BOOLEAN NOT NULL DEFAULT true,
    "level" TEXT NOT NULL DEFAULT 'MUST_HAVE',
    "order" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Criterion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "GoldStandard" (
    "id" TEXT NOT NULL,
    "topicId" TEXT NOT NULL,
    "videoUrl" TEXT NOT NULL,
    "title" TEXT,
    "isPositive" BOOLEAN NOT NULL DEFAULT true,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "GoldStandard_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TopicKeyword" (
    "id" TEXT NOT NULL,
    "topicId" TEXT NOT NULL,
    "keyword" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TopicKeyword_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TopicCreator" (
    "id" TEXT NOT NULL,
    "topicId" TEXT NOT NULL,
    "channelId" TEXT,
    "channelUrl" TEXT,
    "channelName" TEXT,
    "scrapeMonthsBack" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TopicCreator_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "_TopicToVideo" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL,

    CONSTRAINT "_TopicToVideo_AB_pkey" PRIMARY KEY ("A","B")
);

-- CreateIndex
CREATE INDEX "Topic_userId_idx" ON "Topic"("userId");

-- CreateIndex
CREATE INDEX "Criterion_topicId_idx" ON "Criterion"("topicId");

-- CreateIndex
CREATE INDEX "GoldStandard_topicId_idx" ON "GoldStandard"("topicId");

-- CreateIndex
CREATE INDEX "TopicKeyword_topicId_idx" ON "TopicKeyword"("topicId");

-- CreateIndex
CREATE INDEX "TopicCreator_topicId_idx" ON "TopicCreator"("topicId");

-- CreateIndex
CREATE INDEX "_TopicToVideo_B_index" ON "_TopicToVideo"("B");

-- AddForeignKey
ALTER TABLE "Topic" ADD CONSTRAINT "Topic_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Criterion" ADD CONSTRAINT "Criterion_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "GoldStandard" ADD CONSTRAINT "GoldStandard_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TopicKeyword" ADD CONSTRAINT "TopicKeyword_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TopicCreator" ADD CONSTRAINT "TopicCreator_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_TopicToVideo" ADD CONSTRAINT "_TopicToVideo_A_fkey" FOREIGN KEY ("A") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_TopicToVideo" ADD CONSTRAINT "_TopicToVideo_B_fkey" FOREIGN KEY ("B") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AlterTable
ALTER TABLE "Topic" ADD COLUMN     "parentId" TEXT;

-- CreateTable
CREATE TABLE "CriterionFilter" (
    "id" TEXT NOT NULL,
    "topicId" TEXT NOT NULL,
    "criterionId" TEXT NOT NULL,
    "requiredResult" "CriterionResultValue" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CriterionFilter_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "CriterionFilter_topicId_idx" ON "CriterionFilter"("topicId");

-- CreateIndex
CREATE UNIQUE INDEX "CriterionFilter_topicId_criterionId_key" ON "CriterionFilter"("topicId", "criterionId");

-- CreateIndex
CREATE INDEX "Topic_parentId_idx" ON "Topic"("parentId");

-- AddForeignKey
ALTER TABLE "Topic" ADD CONSTRAINT "Topic_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES "Topic"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CriterionFilter" ADD CONSTRAINT "CriterionFilter_topicId_fkey" FOREIGN KEY ("topicId") REFERENCES "Topic"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CriterionFilter" ADD CONSTRAINT "CriterionFilter_criterionId_fkey" FOREIGN KEY ("criterionId") REFERENCES "Criterion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

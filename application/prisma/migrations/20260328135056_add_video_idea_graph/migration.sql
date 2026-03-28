-- CreateEnum
CREATE TYPE "IdeaGraphGenerationStatus" AS ENUM ('IDLE', 'GENERATING', 'COMPLETED', 'FAILED');

-- CreateEnum
CREATE TYPE "IdeaGraphNodeType" AS ENUM ('CLAIM', 'EVIDENCE', 'COUNTERARGUMENT', 'REBUTTAL', 'EXAMPLE', 'ASSUMPTION', 'DEFINITION', 'QUESTION', 'CONCLUSION');

-- CreateEnum
CREATE TYPE "IdeaGraphEdgeType" AS ENUM ('SUPPORTS', 'ATTACKS', 'REBUTS', 'ELABORATES', 'DEPENDS_ON', 'ILLUSTRATES', 'CONTRASTS_WITH');

-- AlterTable
ALTER TABLE "FunnelVideo" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- CreateTable
CREATE TABLE "IdeaGraph" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "videoId" TEXT NOT NULL,
    "generationStatus" "IdeaGraphGenerationStatus" NOT NULL DEFAULT 'IDLE',
    "generationError" TEXT,
    "generatedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "IdeaGraph_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IdeaGraphNode" (
    "id" TEXT NOT NULL,
    "graphId" TEXT NOT NULL,
    "type" "IdeaGraphNodeType" NOT NULL,
    "title" TEXT NOT NULL DEFAULT '',
    "content" TEXT,
    "x" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "y" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "collapsed" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "IdeaGraphNode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IdeaGraphEdge" (
    "id" TEXT NOT NULL,
    "graphId" TEXT NOT NULL,
    "sourceNodeId" TEXT NOT NULL,
    "targetNodeId" TEXT NOT NULL,
    "type" "IdeaGraphEdgeType" NOT NULL,
    "label" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "IdeaGraphEdge_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IdeaGraphNodeSource" (
    "id" TEXT NOT NULL,
    "nodeId" TEXT NOT NULL,
    "paraphrase" TEXT,
    "quote" TEXT NOT NULL,
    "startSec" DOUBLE PRECISION NOT NULL,
    "endSec" DOUBLE PRECISION NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "IdeaGraphNodeSource_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "IdeaGraph_userId_idx" ON "IdeaGraph"("userId");

-- CreateIndex
CREATE INDEX "IdeaGraph_videoId_idx" ON "IdeaGraph"("videoId");

-- CreateIndex
CREATE UNIQUE INDEX "IdeaGraph_userId_videoId_key" ON "IdeaGraph"("userId", "videoId");

-- CreateIndex
CREATE INDEX "IdeaGraphNode_graphId_idx" ON "IdeaGraphNode"("graphId");

-- CreateIndex
CREATE INDEX "IdeaGraphEdge_graphId_idx" ON "IdeaGraphEdge"("graphId");

-- CreateIndex
CREATE INDEX "IdeaGraphEdge_sourceNodeId_idx" ON "IdeaGraphEdge"("sourceNodeId");

-- CreateIndex
CREATE INDEX "IdeaGraphEdge_targetNodeId_idx" ON "IdeaGraphEdge"("targetNodeId");

-- CreateIndex
CREATE INDEX "IdeaGraphNodeSource_nodeId_idx" ON "IdeaGraphNodeSource"("nodeId");

-- AddForeignKey
ALTER TABLE "IdeaGraph" ADD CONSTRAINT "IdeaGraph_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IdeaGraph" ADD CONSTRAINT "IdeaGraph_videoId_fkey" FOREIGN KEY ("videoId") REFERENCES "Video"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IdeaGraphNode" ADD CONSTRAINT "IdeaGraphNode_graphId_fkey" FOREIGN KEY ("graphId") REFERENCES "IdeaGraph"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IdeaGraphEdge" ADD CONSTRAINT "IdeaGraphEdge_graphId_fkey" FOREIGN KEY ("graphId") REFERENCES "IdeaGraph"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IdeaGraphEdge" ADD CONSTRAINT "IdeaGraphEdge_sourceNodeId_fkey" FOREIGN KEY ("sourceNodeId") REFERENCES "IdeaGraphNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IdeaGraphEdge" ADD CONSTRAINT "IdeaGraphEdge_targetNodeId_fkey" FOREIGN KEY ("targetNodeId") REFERENCES "IdeaGraphNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IdeaGraphNodeSource" ADD CONSTRAINT "IdeaGraphNodeSource_nodeId_fkey" FOREIGN KEY ("nodeId") REFERENCES "IdeaGraphNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

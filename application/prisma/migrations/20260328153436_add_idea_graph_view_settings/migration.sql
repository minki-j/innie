-- CreateEnum
CREATE TYPE "IdeaGraphLayoutDirection" AS ENUM ('LR', 'TB');

-- AlterTable
ALTER TABLE "IdeaGraph" ADD COLUMN     "layoutDirection" "IdeaGraphLayoutDirection" NOT NULL DEFAULT 'LR',
ADD COLUMN     "visibleDepth" INTEGER;

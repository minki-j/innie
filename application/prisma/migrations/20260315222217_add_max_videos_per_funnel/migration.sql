-- AlterTable
ALTER TABLE "Funnel" ADD COLUMN     "maxVideosPerCreator" INTEGER NOT NULL DEFAULT 30,
ADD COLUMN     "maxVideosPerKeyword" INTEGER NOT NULL DEFAULT 20;

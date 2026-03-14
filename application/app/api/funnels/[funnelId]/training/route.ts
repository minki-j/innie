import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const RLVR_DEFAULTS = {
  steps: 50,
  groupsPerBatch: 2,
  groupSize: 8,
  maxTokens: 512,
  transcriptMaxChars: 20_000,
};

const SFT_DEFAULTS = {
  batchSize: 4,
  epochs: 1,
  transcriptMaxChars: 20_000,
};

const WORDS_TO_TOKENS_RATIO = 1.3;

function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ funnelId: string }> },
) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { funnelId } = await params;

    const funnel = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
      select: { id: true },
    });

    if (!funnel) {
      return NextResponse.json(
        { error: "Funnel not found" },
        { status: 404 },
      );
    }

    const reviews = await prisma.review.findMany({
      where: {
        userId: session.user.id,
        funnelId,
      },
      select: {
        content: true,
        video: {
          select: { transcript: true, title: true },
        },
      },
    });

    let totalWords = 0;
    let feedbackCount = 0;

    for (const review of reviews) {
      if (!review.video.transcript) continue;

      let feedbackText: string | undefined;

      if (review.content) {
        try {
          const parsed = JSON.parse(review.content);
          feedbackText = parsed.feedback;
        } catch {
          feedbackText = review.content;
        }
      }

      if (!feedbackText) continue;

      feedbackCount++;

      const transcript = review.video.transcript.slice(
        0,
        RLVR_DEFAULTS.transcriptMaxChars,
      );
      const text = `${transcript} ${review.video.title || ""} ${feedbackText}`;
      totalWords += countWords(text);
    }

    let sftTokens = 0;
    let rlvrTokens = 0;

    if (feedbackCount > 0) {
      const avgWordsPerDatapoint = totalWords / feedbackCount;
      const avgTokensPerDatapoint = Math.ceil(
        avgWordsPerDatapoint * WORDS_TO_TOKENS_RATIO,
      );

      sftTokens =
        feedbackCount * avgTokensPerDatapoint * SFT_DEFAULTS.epochs;

      const totalGenerations =
        RLVR_DEFAULTS.steps *
        RLVR_DEFAULTS.groupsPerBatch *
        RLVR_DEFAULTS.groupSize;

      const totalPromptTokens = totalGenerations * avgTokensPerDatapoint;
      const totalCompletionTokens =
        totalGenerations * RLVR_DEFAULTS.maxTokens;

      rlvrTokens = totalPromptTokens + totalCompletionTokens;
    }

    const latestRun = await prisma.trainingRun.findFirst({
      where: { funnelId, userId: session.user.id },
      orderBy: { createdAt: "desc" },
    });

    return NextResponse.json({
      feedbackCount,
      estimatedTokens: {
        sft: sftTokens,
        rlvr: rlvrTokens,
      },
      latestRun: latestRun
        ? {
            id: latestRun.id,
            status: latestRun.status,
            method: latestRun.method,
            modelName: latestRun.modelName,
            version: latestRun.version,
            datasetSize: latestRun.datasetSize,
            isActive: latestRun.isActive,
            error: latestRun.error,
            createdAt: latestRun.createdAt.toISOString(),
            completedAt: latestRun.completedAt?.toISOString() ?? null,
          }
        : null,
      minFeedbackRequired: 5,
    });
  } catch (error) {
    console.error("Error fetching training info:", error);
    return NextResponse.json(
      { error: "Failed to fetch training info" },
      { status: 500 },
    );
  }
}

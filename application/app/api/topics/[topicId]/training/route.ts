import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

/**
 * Training config defaults (must match lab/trains/ configs).
 */
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

/**
 * Approximate tokens from word count.
 * Common heuristic: ~1.3 tokens per English word.
 */
const WORDS_TO_TOKENS_RATIO = 1.3;

function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

/**
 * GET /api/topics/[topicId]/training
 *
 * Returns training info for a topic:
 * - feedbackCount: number of valid feedback reviews (with text + video transcript)
 * - estimatedTokens: { sft, rlvr } approximate total token usage per method
 * - latestRun: the most recent training run (if any)
 * - minFeedbackRequired: minimum feedbacks needed to start training
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ topicId: string }> },
) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;

    // Verify topic ownership
    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
      select: { id: true },
    });

    if (!topic) {
      return NextResponse.json(
        { error: "Topic not found" },
        { status: 404 },
      );
    }

    // Fetch reviews with video transcripts
    const reviews = await prisma.review.findMany({
      where: {
        userId: session.user.id,
        topicId,
      },
      select: {
        content: true,
        video: {
          select: { transcript: true, title: true },
        },
      },
    });

    // Filter valid feedbacks: must have feedback text and video must have transcript
    let totalWords = 0;
    let feedbackCount = 0;

    for (const review of reviews) {
      if (!review.video.transcript) continue;

      let content: { feedback?: string } = {};
      if (review.content) {
        try {
          content = JSON.parse(review.content);
        } catch {
          continue;
        }
      }

      if (!content.feedback) continue;

      feedbackCount++;

      // Count words in truncated transcript + title + feedback
      const transcript = review.video.transcript.slice(
        0,
        RLVR_DEFAULTS.transcriptMaxChars,
      );
      const text = `${transcript} ${review.video.title || ""} ${content.feedback}`;
      totalWords += countWords(text);
    }

    // Estimate tokens per method
    let sftTokens = 0;
    let rlvrTokens = 0;

    if (feedbackCount > 0) {
      const avgWordsPerDatapoint = totalWords / feedbackCount;
      const avgTokensPerDatapoint = Math.ceil(
        avgWordsPerDatapoint * WORDS_TO_TOKENS_RATIO,
      );

      // --- SFT estimate ---
      // Each datapoint is processed once per epoch.
      // Tokens = feedbackCount * avgTokensPerDatapoint * epochs
      sftTokens =
        feedbackCount * avgTokensPerDatapoint * SFT_DEFAULTS.epochs;

      // --- RLVR estimate ---
      // Total generations = steps * groupsPerBatch * groupSize
      const totalGenerations =
        RLVR_DEFAULTS.steps *
        RLVR_DEFAULTS.groupsPerBatch *
        RLVR_DEFAULTS.groupSize;

      // Prompt tokens: each generation processes a full prompt
      const totalPromptTokens = totalGenerations * avgTokensPerDatapoint;

      // Completion tokens: each generation produces up to maxTokens
      const totalCompletionTokens =
        totalGenerations * RLVR_DEFAULTS.maxTokens;

      rlvrTokens = totalPromptTokens + totalCompletionTokens;
    }

    // Fetch the latest training run for this topic
    const latestRun = await prisma.trainingRun.findFirst({
      where: { topicId, userId: session.user.id },
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

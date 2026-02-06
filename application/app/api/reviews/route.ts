import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

const RATING_MAP: Record<string, number> = {
  dislike: 1,
  neutral: 3,
  like: 5,
};

const REVERSE_RATING_MAP: Record<number, string> = {
  1: 'dislike',
  3: 'neutral',
  5: 'like',
};

export async function GET(request: NextRequest) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      );
    }

    const searchParams = request.nextUrl.searchParams;
    const videoId = searchParams.get('videoId');
    const topicId = searchParams.get('topicId');

    if (!videoId) {
      return NextResponse.json(
        { error: 'videoId is required' },
        { status: 400 }
      );
    }

    // Try the composite key first, fall back to a manual query for null topicId
    let review;
    if (topicId) {
      review = await prisma.review.findUnique({
        where: {
          userId_videoId_topicId: {
            userId: session.user.id,
            videoId,
            topicId,
          },
        },
      });
    } else {
      review = await prisma.review.findFirst({
        where: {
          userId: session.user.id,
          videoId,
          topicId: null,
        },
      });
    }

    if (!review) {
      // Even without a review, check if a GoldStandard exists for this video+topic
      if (topicId) {
        const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;
        const existingGoldStandard = await prisma.goldStandard.findFirst({
          where: { topicId, videoUrl },
        });
        if (existingGoldStandard) {
          return NextResponse.json({
            rating: null,
            likeAspects: [],
            feedback: '',
            includeInTestSet: true,
          });
        }
      }
      return NextResponse.json(null);
    }

    // Parse the content JSON and map rating back to string
    let parsedContent: { likeAspects?: string[]; feedback?: string; includeInTestSet?: boolean } = {};
    if (review.content) {
      try {
        parsedContent = JSON.parse(review.content);
      } catch {
        // content is not valid JSON, ignore
      }
    }

    // Also check if a GoldStandard record exists (may have been added from topic settings)
    let includeInTestSet = parsedContent.includeInTestSet ?? false;
    if (topicId && !includeInTestSet) {
      const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;
      const existingGoldStandard = await prisma.goldStandard.findFirst({
        where: { topicId, videoUrl },
      });
      if (existingGoldStandard) {
        includeInTestSet = true;
      }
    }

    return NextResponse.json({
      rating: REVERSE_RATING_MAP[review.rating] ?? null,
      likeAspects: parsedContent.likeAspects ?? [],
      feedback: parsedContent.feedback ?? '',
      includeInTestSet,
    });
  } catch (error) {
    console.error('Error fetching review:', error);
    return NextResponse.json(
      { error: 'Failed to fetch review' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      );
    }

    const body = await request.json();
    const { videoId, topicId, rating, likeAspects, feedback, includeInTestSet } = body;

    if (!videoId || !rating) {
      return NextResponse.json(
        { error: 'videoId and rating are required' },
        { status: 400 }
      );
    }

    const numericRating = RATING_MAP[rating];
    if (numericRating === undefined) {
      return NextResponse.json(
        { error: 'Invalid rating value. Must be one of: dislike, neutral, like' },
        { status: 400 }
      );
    }

    // Store extra data as JSON in the content field
    const content = JSON.stringify({
      likeAspects: likeAspects ?? [],
      feedback: feedback ?? '',
      includeInTestSet: includeInTestSet ?? false,
    });

    let review;
    if (topicId) {
      review = await prisma.review.upsert({
        where: {
          userId_videoId_topicId: {
            userId: session.user.id,
            videoId,
            topicId,
          },
        },
        update: {
          rating: numericRating,
          content,
        },
        create: {
          userId: session.user.id,
          videoId,
          topicId,
          rating: numericRating,
          content,
        },
      });

      // Sync GoldStandard record based on includeInTestSet toggle
      const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;

      if (includeInTestSet) {
        // Check if a GoldStandard already exists for this topic + video URL
        const existingGoldStandard = await prisma.goldStandard.findFirst({
          where: { topicId, videoUrl },
        });

        if (!existingGoldStandard) {
          // Fetch video title for display
          const video = await prisma.video.findUnique({
            where: { id: videoId },
            select: { title: true },
          });

          const isPositive = rating !== 'dislike';

          await prisma.goldStandard.create({
            data: {
              topicId,
              videoUrl,
              title: video?.title ?? null,
              isPositive,
              note: feedback?.trim() || null,
            },
          });
        }
      } else {
        // Remove GoldStandard if it exists for this topic + video URL
        const existingGoldStandard = await prisma.goldStandard.findFirst({
          where: { topicId, videoUrl },
        });

        if (existingGoldStandard) {
          await prisma.goldStandard.delete({
            where: { id: existingGoldStandard.id },
          });
        }
      }
    } else {
      // For reviews without a topic, find existing or create
      const existing = await prisma.review.findFirst({
        where: {
          userId: session.user.id,
          videoId,
          topicId: null,
        },
      });

      if (existing) {
        review = await prisma.review.update({
          where: { id: existing.id },
          data: { rating: numericRating, content },
        });
      } else {
        review = await prisma.review.create({
          data: {
            userId: session.user.id,
            videoId,
            rating: numericRating,
            content,
          },
        });
      }
    }

    return NextResponse.json(review);
  } catch (error) {
    console.error('Error saving review:', error);
    return NextResponse.json(
      { error: 'Failed to save review' },
      { status: 500 }
    );
  }
}

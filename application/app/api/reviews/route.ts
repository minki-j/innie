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
    const funnelId = searchParams.get('funnelId');

    if (!videoId) {
      return NextResponse.json(
        { error: 'videoId is required' },
        { status: 400 }
      );
    }

    let review;
    if (funnelId) {
      review = await prisma.review.findUnique({
        where: {
          userId_videoId_funnelId: {
            userId: session.user.id,
            videoId,
            funnelId,
          },
        },
      });
    } else {
      review = await prisma.review.findFirst({
        where: {
          userId: session.user.id,
          videoId,
          funnelId: null,
        },
      });
    }

    if (!review) {
      return NextResponse.json(null);
    }

    let parsedContent: { likeAspects?: string[]; feedback?: string; includeInTestSet?: boolean } = {};
    if (review.content) {
      try {
        parsedContent = JSON.parse(review.content);
      } catch {
        parsedContent = { feedback: review.content };
      }
    }

    return NextResponse.json({
      rating: REVERSE_RATING_MAP[review.rating] ?? null,
      likeAspects: parsedContent.likeAspects ?? [],
      feedback: parsedContent.feedback ?? '',
      includeInTestSet: parsedContent.includeInTestSet ?? false,
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
    const { videoId, funnelId, rating, likeAspects, feedback } = body;

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

    const content = JSON.stringify({
      likeAspects: likeAspects ?? [],
      feedback: feedback ?? '',
    });

    let review;
    if (funnelId) {
      review = await prisma.review.upsert({
        where: {
          userId_videoId_funnelId: {
            userId: session.user.id,
            videoId,
            funnelId,
          },
        },
        update: {
          rating: numericRating,
          content,
        },
        create: {
          userId: session.user.id,
          videoId,
          funnelId,
          rating: numericRating,
          content,
        },
      });
    } else {
      const existing = await prisma.review.findFirst({
        where: {
          userId: session.user.id,
          videoId,
          funnelId: null,
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

import { prisma } from "@/lib/prisma";
import { auth } from "@/lib/auth";

export async function getUserTopics() {
  const session = await auth();
  if (!session?.user?.id) return [];

  return prisma.topic.findMany({
    where: { userId: session.user.id },
    select: { id: true, name: true },
    orderBy: { createdAt: "desc" },
  });
}

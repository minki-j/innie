import { prisma } from "@/lib/prisma";
import { auth } from "@/lib/auth";

export async function getUserFunnels() {
  const session = await auth();
  if (!session?.user?.id) return [];

  return prisma.funnel.findMany({
    where: { userId: session.user.id },
    select: {
      id: true,
      name: true,
      classNodes: {
        select: { id: true, title: true },
        orderBy: { createdAt: "asc" },
      },
    },
    orderBy: { createdAt: "desc" },
  });
}

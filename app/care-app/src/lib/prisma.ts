import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["error", "warn"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;

function isClosedConnectionError(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return /closed|connection.*terminated|ECONNRESET|kind: Closed/i.test(msg);
}

/** Run a Prisma query; reconnect once if Neon/pooler closed an idle connection. */
export async function withPrisma<T>(fn: (db: PrismaClient) => Promise<T>): Promise<T> {
  try {
    return await fn(prisma);
  } catch (e) {
    if (!isClosedConnectionError(e)) throw e;
    await prisma.$disconnect();
    await prisma.$connect();
    return await fn(prisma);
  }
}

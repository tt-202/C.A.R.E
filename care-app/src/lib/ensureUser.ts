import { prisma } from "@/lib/prisma";

export async function ensureUser(
  firebaseUid: string,
  opts?: { email?: string | null; displayName?: string | null }
) {
  return prisma.user.upsert({
    where: { firebaseUid },
    create: {
      firebaseUid,
      email: opts?.email ?? "",
      displayName: opts?.displayName ?? "",
    },
    update: {
      ...(opts?.email != null ? { email: opts.email } : {}),
      ...(opts?.displayName != null ? { displayName: opts.displayName } : {}),
    },
  });
}

import { prisma } from "@/lib/prisma";

export async function ensureUser(
  firebaseUid: string,
  opts?: {
    email?: string | null;
    displayName?: string | null;
    careRecipientName?: string | null;
    caregiverName?: string | null;
    breakfastTime?: string | null;
    lunchTime?: string | null;
    dinnerTime?: string | null;
  }
) {
  return prisma.user.upsert({
    where: { firebaseUid },
    create: {
      firebaseUid,
      email: opts?.email ?? "",
      displayName: opts?.displayName ?? "",
      careRecipientName: opts?.careRecipientName ?? "",
      caregiverName: opts?.caregiverName ?? "",
      breakfastTime: opts?.breakfastTime ?? "08:00",
      lunchTime: opts?.lunchTime ?? "12:30",
      dinnerTime: opts?.dinnerTime ?? "18:00",
    },
    update: {
      ...(opts?.email != null ? { email: opts.email } : {}),
      ...(opts?.displayName != null ? { displayName: opts.displayName } : {}),
      ...(opts?.careRecipientName != null ? { careRecipientName: opts.careRecipientName } : {}),
      ...(opts?.caregiverName != null ? { caregiverName: opts.caregiverName } : {}),
      ...(opts?.breakfastTime != null ? { breakfastTime: opts.breakfastTime } : {}),
      ...(opts?.lunchTime != null ? { lunchTime: opts.lunchTime } : {}),
      ...(opts?.dinnerTime != null ? { dinnerTime: opts.dinnerTime } : {}),
    },
  });
}

import { randomBytes } from "crypto";
import type { CareMemberRole, CarePair, CarePairMember, User } from "@prisma/client";
import { withPrisma } from "@/lib/prisma";
import { ensureUser } from "@/lib/ensureUser";
import { normalizeMealSchedule } from "@/lib/mealSchedule";
import { resolveMealTimezone } from "@/lib/mealReminderTimezone";
import { syncCarePairMember } from "@/lib/carePairFirestore";

export type { CareMemberRole };

const INVITE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export type CareContext = {
  user: User;
  member: (CarePairMember & { carePair: CarePair }) | null;
  carePairId: string | null;
  role: CareMemberRole | null;
};

export type CarePairProfile = {
  carePairId: string;
  role: CareMemberRole;
  careRecipientName: string;
  caregiverName: string;
  breakfastTime: string;
  lunchTime: string;
  dinnerTime: string;
  timezone: string;
  members: { role: CareMemberRole; email: string }[];
  linkedUser: boolean;
  linkedCaregiver: boolean;
};

function generateInviteCode(): string {
  return randomBytes(4).toString("hex").toUpperCase();
}

async function findMember(firebaseUid: string) {
  return withPrisma((prisma) =>
    prisma.carePairMember.findUnique({
      where: { firebaseUid },
      include: { carePair: true },
    }),
  );
}

async function migrateLegacyUser(user: User, defaultRole: CareMemberRole = "caregiver") {
  const names = user.careRecipientName.trim() && user.caregiverName.trim();
  if (!names) return null;

  const schedule = normalizeMealSchedule(user);
  return withPrisma(async (prisma) => {
    const pair = await prisma.carePair.create({
      data: {
        careRecipientName: user.careRecipientName,
        caregiverName: user.caregiverName,
        breakfastTime: schedule.breakfastTime,
        lunchTime: schedule.lunchTime,
        dinnerTime: schedule.dinnerTime,
      },
    });

    const member = await prisma.carePairMember.create({
      data: {
        carePairId: pair.id,
        firebaseUid: user.firebaseUid,
        role: defaultRole,
        email: user.email,
      },
      include: { carePair: true },
    });

    await prisma.meal.updateMany({
      where: { userId: user.id, carePairId: null },
      data: { carePairId: pair.id },
    });

    await syncCarePairMember(pair.id, user.firebaseUid, defaultRole);
    return member;
  });
}

export async function getCareContext(
  firebaseUid: string,
  opts?: {
    email?: string | null;
    displayName?: string | null;
  },
): Promise<CareContext> {
  const user = await ensureUser(firebaseUid, opts);
  let member = await findMember(firebaseUid);
  if (!member) {
    member = await migrateLegacyUser(user);
  }
  return {
    user,
    member,
    carePairId: member?.carePairId ?? null,
    role: member?.role ?? null,
  };
}

export function carePairToProfile(
  pair: CarePair,
  role: CareMemberRole,
  members: { role: CareMemberRole; email: string }[],
): CarePairProfile {
  const schedule = normalizeMealSchedule(pair);
  return {
    carePairId: pair.id,
    role,
    careRecipientName: pair.careRecipientName,
    caregiverName: pair.caregiverName,
    ...schedule,
    timezone: resolveMealTimezone(pair.timezone),
    members,
    linkedUser: members.some((m) => m.role === "user"),
    linkedCaregiver: members.some((m) => m.role === "caregiver"),
  };
}

export async function createCarePairForCaregiver(
  firebaseUid: string,
  opts: {
    email?: string | null;
    displayName?: string | null;
    careRecipientName: string;
    caregiverName: string;
    breakfastTime?: string;
    lunchTime?: string;
    dinnerTime?: string;
    timezone?: string;
  },
): Promise<CarePairProfile> {
  const existing = await findMember(firebaseUid);
  if (existing) {
    throw new Error("Already linked to a care pair");
  }

  const user = await ensureUser(firebaseUid, {
    email: opts.email,
    displayName: opts.displayName ?? opts.caregiverName,
    careRecipientName: opts.careRecipientName,
    caregiverName: opts.caregiverName,
    breakfastTime: opts.breakfastTime,
    lunchTime: opts.lunchTime,
    dinnerTime: opts.dinnerTime,
  });

  const schedule = normalizeMealSchedule({
    breakfastTime: opts.breakfastTime,
    lunchTime: opts.lunchTime,
    dinnerTime: opts.dinnerTime,
  });

  const member = await withPrisma(async (prisma) => {
    const pair = await prisma.carePair.create({
      data: {
        careRecipientName: opts.careRecipientName,
        caregiverName: opts.caregiverName,
        timezone: resolveMealTimezone(opts.timezone),
        ...schedule,
      },
    });

    return prisma.carePairMember.create({
      data: {
        carePairId: pair.id,
        firebaseUid,
        role: "caregiver",
        email: user.email,
      },
      include: { carePair: true },
    });
  });

  await syncCarePairMember(member.carePairId, firebaseUid, "caregiver");
  return carePairToProfile(member.carePair, "caregiver", [
    { role: "caregiver", email: user.email },
  ]);
}

export async function updateCarePairProfile(
  firebaseUid: string,
  data: {
    careRecipientName?: string;
    caregiverName?: string;
    breakfastTime?: string;
    lunchTime?: string;
    dinnerTime?: string;
    timezone?: string;
  },
): Promise<CarePairProfile> {
  const ctx = await getCareContext(firebaseUid);
  if (!ctx.member) {
    throw new Error("Not linked to a care pair");
  }

  const schedule = normalizeMealSchedule({
    breakfastTime: data.breakfastTime ?? ctx.member.carePair.breakfastTime,
    lunchTime: data.lunchTime ?? ctx.member.carePair.lunchTime,
    dinnerTime: data.dinnerTime ?? ctx.member.carePair.dinnerTime,
  });

  const pair = await withPrisma((prisma) =>
    prisma.carePair.update({
      where: { id: ctx.member!.carePairId },
      data: {
        ...(data.careRecipientName != null
          ? { careRecipientName: data.careRecipientName }
          : {}),
        ...(data.caregiverName != null ? { caregiverName: data.caregiverName } : {}),
        ...schedule,
        ...(data.timezone != null
          ? { timezone: resolveMealTimezone(data.timezone) }
          : {}),
      },
    }),
  );

  await ensureUser(firebaseUid, {
    careRecipientName: pair.careRecipientName,
    caregiverName: pair.caregiverName,
    breakfastTime: pair.breakfastTime,
    lunchTime: pair.lunchTime,
    dinnerTime: pair.dinnerTime,
  });

  const members = await listPairMembers(pair.id);
  return carePairToProfile(pair, ctx.member.role, members);
}

async function listPairMembers(carePairId: string) {
  const rows = await withPrisma((prisma) =>
    prisma.carePairMember.findMany({
      where: { carePairId },
      select: { role: true, email: true },
    }),
  );
  return rows.map((r) => ({ role: r.role, email: r.email }));
}

export async function loadCarePairProfile(firebaseUid: string): Promise<CarePairProfile | null> {
  const ctx = await getCareContext(firebaseUid);
  if (!ctx.member) return null;
  const members = await listPairMembers(ctx.member.carePairId);
  return carePairToProfile(ctx.member.carePair, ctx.member.role, members);
}

export async function createCareInvite(
  firebaseUid: string,
  role: CareMemberRole = "user",
): Promise<{ code: string; expiresAt: string; role: CareMemberRole }> {
  const ctx = await getCareContext(firebaseUid);
  if (!ctx.member || ctx.member.role !== "caregiver") {
    throw new Error("Only caregivers can create invites");
  }

  const members = await listPairMembers(ctx.member.carePairId);
  if (members.some((m) => m.role === role)) {
    throw new Error(`A ${role} is already linked to this care pair`);
  }

  const expiresAt = new Date(Date.now() + INVITE_TTL_MS);
  let code = generateInviteCode();
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await withPrisma((prisma) =>
        prisma.careInvite.create({
          data: {
            carePairId: ctx.member!.carePairId,
            code,
            role,
            createdByUid: firebaseUid,
            expiresAt,
          },
        }),
      );
      return { code, expiresAt: expiresAt.toISOString(), role };
    } catch {
      code = generateInviteCode();
    }
  }
  throw new Error("Could not create invite");
}

export async function previewCareInvite(code: string) {
  const invite = await withPrisma((prisma) =>
    prisma.careInvite.findUnique({
      where: { code: code.trim().toUpperCase() },
      include: { carePair: true },
    }),
  );
  if (!invite || invite.acceptedAt || invite.expiresAt < new Date()) {
    return null;
  }
  return {
    role: invite.role,
    careRecipientName: invite.carePair.careRecipientName,
    caregiverName: invite.carePair.caregiverName,
    expiresAt: invite.expiresAt.toISOString(),
  };
}

export async function acceptCareInvite(
  firebaseUid: string,
  code: string,
  opts?: { email?: string | null; displayName?: string | null },
): Promise<CarePairProfile> {
  const normalized = code.trim().toUpperCase();
  const existing = await findMember(firebaseUid);
  if (existing) {
    throw new Error("This account is already linked to a care pair");
  }

  const user = await ensureUser(firebaseUid, opts);

  return withPrisma(async (prisma) => {
    const invite = await prisma.careInvite.findUnique({
      where: { code: normalized },
      include: { carePair: true },
    });
    if (!invite || invite.acceptedAt) {
      throw new Error("Invite not found or already used");
    }
    if (invite.expiresAt < new Date()) {
      throw new Error("Invite has expired");
    }

    const roleTaken = await prisma.carePairMember.findFirst({
      where: { carePairId: invite.carePairId, role: invite.role },
    });
    if (roleTaken) {
      throw new Error(`This care pair already has a ${invite.role}`);
    }

    const member = await prisma.carePairMember.create({
      data: {
        carePairId: invite.carePairId,
        firebaseUid,
        role: invite.role,
        email: user.email,
      },
      include: { carePair: true },
    });

    await prisma.careInvite.update({
      where: { id: invite.id },
      data: { acceptedAt: new Date(), acceptedByUid: firebaseUid },
    });

    await ensureUser(firebaseUid, {
      careRecipientName: invite.carePair.careRecipientName,
      caregiverName: invite.carePair.caregiverName,
      breakfastTime: invite.carePair.breakfastTime,
      lunchTime: invite.carePair.lunchTime,
      dinnerTime: invite.carePair.dinnerTime,
    });

    await syncCarePairMember(invite.carePairId, firebaseUid, invite.role);

    const members = await listPairMembers(invite.carePairId);
    return carePairToProfile(member.carePair, member.role, members);
  });
}

export type MealScope = {
  userId: string;
  carePairId: string | null;
};

export async function getMealScope(firebaseUid: string, opts?: { email?: string | null; displayName?: string | null }): Promise<MealScope> {
  const ctx = await getCareContext(firebaseUid, opts);
  return {
    userId: ctx.user.id,
    carePairId: ctx.carePairId,
  };
}

export function mealOwnershipWhere(scope: MealScope) {
  if (scope.carePairId) {
    return {
      OR: [{ carePairId: scope.carePairId }, { userId: scope.userId, carePairId: null }],
    };
  }
  return { userId: scope.userId };
}

export async function listCaregiverFirebaseUidsForPair(carePairId: string): Promise<string[]> {
  const rows = await withPrisma((prisma) =>
    prisma.carePairMember.findMany({
      where: { carePairId, role: "caregiver" },
      select: { firebaseUid: true },
    }),
  );
  return rows.map((r) => r.firebaseUid);
}

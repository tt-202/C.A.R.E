-- CreateEnum
CREATE TYPE "CareMemberRole" AS ENUM ('caregiver', 'user');

-- CreateTable
CREATE TABLE "CarePair" (
    "id" TEXT NOT NULL,
    "careRecipientName" TEXT NOT NULL DEFAULT '',
    "caregiverName" TEXT NOT NULL DEFAULT '',
    "breakfastTime" TEXT NOT NULL DEFAULT '08:00',
    "lunchTime" TEXT NOT NULL DEFAULT '12:30',
    "dinnerTime" TEXT NOT NULL DEFAULT '18:00',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CarePair_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CarePairMember" (
    "id" TEXT NOT NULL,
    "carePairId" TEXT NOT NULL,
    "firebaseUid" TEXT NOT NULL,
    "role" "CareMemberRole" NOT NULL,
    "email" TEXT NOT NULL DEFAULT '',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CarePairMember_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CareInvite" (
    "id" TEXT NOT NULL,
    "carePairId" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "role" "CareMemberRole" NOT NULL,
    "createdByUid" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "acceptedAt" TIMESTAMP(3),
    "acceptedByUid" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CareInvite_pkey" PRIMARY KEY ("id")
);

-- AlterTable
ALTER TABLE "Meal" ADD COLUMN "carePairId" TEXT,
ALTER COLUMN "userId" DROP NOT NULL;

-- CreateIndex
CREATE UNIQUE INDEX "CarePairMember_firebaseUid_key" ON "CarePairMember"("firebaseUid");

-- CreateIndex
CREATE INDEX "CarePairMember_carePairId_idx" ON "CarePairMember"("carePairId");

-- CreateIndex
CREATE INDEX "CarePairMember_carePairId_role_idx" ON "CarePairMember"("carePairId", "role");

-- CreateIndex
CREATE UNIQUE INDEX "CareInvite_code_key" ON "CareInvite"("code");

-- CreateIndex
CREATE INDEX "CareInvite_carePairId_idx" ON "CareInvite"("carePairId");

-- CreateIndex
CREATE INDEX "Meal_carePairId_idx" ON "Meal"("carePairId");

-- AddForeignKey
ALTER TABLE "CarePairMember" ADD CONSTRAINT "CarePairMember_carePairId_fkey" FOREIGN KEY ("carePairId") REFERENCES "CarePair"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CareInvite" ADD CONSTRAINT "CareInvite_carePairId_fkey" FOREIGN KEY ("carePairId") REFERENCES "CarePair"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Meal" ADD CONSTRAINT "Meal_carePairId_fkey" FOREIGN KEY ("carePairId") REFERENCES "CarePair"("id") ON DELETE CASCADE ON UPDATE CASCADE;

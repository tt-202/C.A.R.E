-- Bite hold at mouth (seconds) — editable by user and caregiver in care-app.
ALTER TABLE "CarePair" ADD COLUMN "biteHoldSeconds" DOUBLE PRECISION NOT NULL DEFAULT 2;

-- Meal reminder times are local wall-clock; store IANA timezone per care pair.
ALTER TABLE "CarePair" ADD COLUMN "timezone" TEXT NOT NULL DEFAULT 'America/New_York';

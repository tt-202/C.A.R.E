import type { Meal } from "@prisma/client";
import type { MealHistoryEntry } from "@/mealHistoryStorage";

export function mealToHistoryEntry(meal: Meal): MealHistoryEntry {
  if (!meal.endedAt) {
    throw new Error("Meal must be ended to build history entry");
  }
  return {
    id: meal.id,
    endedAt: meal.endedAt.toISOString(),
    durationMs: meal.durationMs ?? 0,
    bitesTotal: meal.bitesTotal,
    bySection: {
      1: meal.section1Count,
      2: meal.section2Count,
      3: meal.section3Count,
      4: meal.section4Count,
    },
    plannedMealTime: meal.plannedMealTime ?? undefined,
  };
}

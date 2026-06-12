/** Firestore paths under robots/{robotId}/… written by the Jetson worker. */

export type RobotLiveStatus = {
  state?: string;
  bite_count?: number;
  section?: number;
  last_feed_time?: unknown;
  emergency?: boolean;
  jetson_online?: boolean;
};

export type RobotFeedCounts = {
  total_bites?: number;
  successful_feeds?: number;
  failed_feeds?: number;
  /** Legacy field names from early Jetson scripts. */
  eat_press_count?: number;
  total_feed_attempts?: number;
};

export type RobotButtonInput = {
  eat_pressed?: boolean;
  stop_pressed?: boolean;
  last_pin?: number;
};

export function robotLiveStatusPath(robotId: string) {
  return ["robots", robotId, "status", "live"] as const;
}

export function robotFeedCountsPath(robotId: string) {
  return ["robots", robotId, "stats", "feed_counts"] as const;
}

export function robotButtonInputPath(robotId: string) {
  return ["robots", robotId, "status", "button_input"] as const;
}

export function feedCountTotal(counts: RobotFeedCounts | null | undefined): number {
  if (!counts) return 0;
  if (typeof counts.total_bites === "number") return counts.total_bites;
  if (typeof counts.eat_press_count === "number") return counts.eat_press_count;
  return 0;
}

import type {
  RobotButtonInput,
  RobotFeedCounts,
  RobotLiveStatus,
} from "@/lib/robotFirestorePaths";

export type RobotFirestoreSnapshot = {
  robotId: string;
  live: RobotLiveStatus | null;
  feedCounts: RobotFeedCounts | null;
  buttonInput: RobotButtonInput | null;
  fetchedAt: string;
  stale: boolean;
  clearedStale: boolean;
  clearedHistory?: boolean;
};

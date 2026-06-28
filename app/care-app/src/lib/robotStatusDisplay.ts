import type { RobotButtonInput, RobotLiveStatus } from "@/lib/robotFirestorePaths";
import { isRobotStatusFresh } from "@/lib/robotStatusTime";

export function isJetsonEffectivelyOnline(live: RobotLiveStatus | null | undefined): boolean {
  if (!live) return false;
  return Boolean(live.jetson_online) && isRobotStatusFresh(live.updatedAt);
}

/** Session fields only — lifetime stats stay visible when offline. */
export function displayRobotLive(live: RobotLiveStatus | null | undefined): RobotLiveStatus | null {
  if (!live) return null;
  if (isJetsonEffectivelyOnline(live)) return live;
  return {
    ...live,
    state: "OFFLINE",
    bite_count: 0,
    section: undefined,
    emergency: false,
    last_feed_time: undefined,
  };
}

export function displayRobotButtons(
  buttons: RobotButtonInput | null | undefined,
  live: RobotLiveStatus | null | undefined,
): RobotButtonInput | null {
  if (!buttons) return null;
  if (isJetsonEffectivelyOnline(live)) return buttons;
  return {
    eat_pressed: false,
    stop_pressed: false,
    eat_press_seq: undefined,
    last_pin: undefined,
  };
}

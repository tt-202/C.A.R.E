import type { RobotCommandPayload, RobotCommandType } from "@/lib/robot";
import type { RobotFirestoreSnapshot } from "@/lib/robotStatusTypes";

const robotEnabled =
  typeof process !== "undefined" &&
  process.env.NEXT_PUBLIC_ROBOT_ENABLED === "true";

export function isRobotControlEnabled(): boolean {
  return robotEnabled;
}

export async function sendRobotCommand(
  getIdToken: () => Promise<string>,
  cmd: RobotCommandType,
  payload?: RobotCommandPayload,
): Promise<{ commandId: string; robotId: string } | null> {
  if (!robotEnabled) return null;

  const token = await getIdToken();
  const res = await fetch("/api/robot/command", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ cmd, payload }),
  });
  if (!res.ok) {
    throw new Error("robot command failed");
  }
  return (await res.json()) as { commandId: string; robotId: string };
}

export async function refreshRobotLiveStatus(
  getIdToken: () => Promise<string>,
  robotId: string,
  opts?: { clearHistory?: boolean },
): Promise<RobotFirestoreSnapshot> {
  const token = await getIdToken();
  const res = await fetch("/api/robot/status/refresh", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      robotId,
      clearHistory: opts?.clearHistory !== false,
    }),
  });
  const data = (await res.json()) as RobotFirestoreSnapshot & { error?: string };
  if (!res.ok) {
    throw new Error(data.error ?? "robot status refresh failed");
  }
  return data;
}

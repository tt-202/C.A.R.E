/** Commands the Jetson worker may execute (allowlist on server + worker). */
export const ROBOT_COMMANDS = ["home", "next_bite", "pause", "stop"] as const;

export type RobotCommandType = (typeof ROBOT_COMMANDS)[number];

export type RobotCommandStatus = "pending" | "running" | "done" | "error";

export type RobotCommandPayload = {
  sectionNum?: number;
  mealId?: string;
};

export function isRobotCommandType(value: string): value is RobotCommandType {
  return (ROBOT_COMMANDS as readonly string[]).includes(value);
}

export function getRobotId(): string {
  return process.env.ROBOT_ID?.trim() || "care-01";
}

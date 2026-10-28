// The run status badge: always an icon and a word, never color alone (UI_SPEC §2).
import type { RunStatus } from "../api/types";
import { Icon, type IconName } from "./Icon";
import "./StatusBadge.css";

/** How one status looks: its word, its icon and its color group. */
interface BadgeStyle {
  word: string;
  icon: IconName;
  tone: "blue" | "red" | "green" | "grey";
}

// Every processing status shares one look: the run is still being worked on
const PROCESSING_BADGE: BadgeStyle = { word: "Processing", icon: "clock", tone: "grey" };

// One entry per API status; the Record type makes the compiler check none is missing
export const BADGE_BY_STATUS: Record<RunStatus, BadgeStyle> = {
  created: PROCESSING_BADGE,
  ingesting: PROCESSING_BADGE,
  extracting: PROCESSING_BADGE,
  verifying_extraction: PROCESSING_BADGE,
  transforming: PROCESSING_BADGE,
  validating: PROCESSING_BADGE,
  in_review: { word: "Ready for review", icon: "eye", tone: "blue" },
  rechecking: { word: "Re-checking", icon: "refresh", tone: "blue" },
  failed: { word: "Failed", icon: "cross-circle", tone: "red" },
};

// A run in review with the verified label
const VERIFIED_BADGE: BadgeStyle = { word: "Verified", icon: "check", tone: "green" };

/** Props of the badge: the run status and whether the run has the verified label. */
interface StatusBadgeProps {
  status: RunStatus;
  isVerified?: boolean;
}

/** Show a run's status as a colored pill with an icon and a word. */
export function StatusBadge({ status, isVerified = false }: StatusBadgeProps) {
  const badge = isVerified && status === "in_review" ? VERIFIED_BADGE : BADGE_BY_STATUS[status];
  return (
    <span className={`status-badge status-badge--${badge.tone}`}>
      <Icon name={badge.icon} size={14} strokeWidth={2.2} />
      {badge.word}
    </span>
  );
}

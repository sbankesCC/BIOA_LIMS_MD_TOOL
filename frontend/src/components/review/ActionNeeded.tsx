// Icon-and-word labels for a record's action needed (Fix / Check / None / Excluded) and for
// an issue's severity. Color is never used alone (UI_SPEC §2).
import type { IssueSummary, ReviewRow } from "../../api/types";
import { Icon, type IconName } from "../Icon";
import "./ActionNeeded.css";

/** How one label looks: its word, icon and color group. */
interface LabelStyle {
  word: string;
  icon: IconName;
  tone: "red" | "amber" | "green" | "grey";
}

// One style per action needed value; the Record type makes the compiler check none is missing
const ACTION_STYLES: Record<ReviewRow["action_needed"], LabelStyle> = {
  fix: { word: "Fix", icon: "cross-circle", tone: "red" },
  check: { word: "Check", icon: "warning", tone: "amber" },
  none: { word: "None", icon: "check", tone: "green" },
  excluded: { word: "Excluded", icon: "ban", tone: "grey" },
};

// One style per issue severity
export const SEVERITY_STYLES: Record<IssueSummary["severity"], LabelStyle> = {
  error: { word: "Fix", icon: "cross-circle", tone: "red" },
  warning: { word: "Check", icon: "warning", tone: "amber" },
  info: { word: "Info", icon: "info", tone: "grey" },
};

/** Show a record's action needed as an icon and a word. */
export function ActionNeededLabel({ action }: { action: ReviewRow["action_needed"] }) {
  const style = ACTION_STYLES[action];
  return (
    <span className={`action-label action-label--${style.tone}`}>
      <Icon name={style.icon} size={16} strokeWidth={2} />
      {style.word}
    </span>
  );
}

/** Show an issue's severity icon, with its word for screen readers. */
export function SeverityIcon({ severity }: { severity: IssueSummary["severity"] }) {
  const style = SEVERITY_STYLES[severity];
  return (
    <span className={`action-label action-label--${style.tone}`}>
      <Icon name={style.icon} size={16} strokeWidth={2} />
      <span className="visually-hidden">{style.word}</span>
    </span>
  );
}

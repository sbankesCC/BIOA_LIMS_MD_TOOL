// The summary strip (UI_SPEC §4.3): records, issues to fix, warnings and excluded records,
// and the grid filters All / Needs action / Excluded.
import type { ReviewCounts } from "../../api/types";
import type { RowFilter } from "../../lib/reviewIssues";
import { Icon } from "../Icon";
import "./SummaryStrip.css";

/** Props of the strip: the counts, the current filter and what picking a filter does. */
interface SummaryStripProps {
  counts: ReviewCounts;
  filter: RowFilter;
  onFilter: (filter: RowFilter) => void;
}

/** Show the counts and the filter buttons. */
export function SummaryStrip({ counts, filter, onFilter }: SummaryStripProps) {
  // Each filter button: its value, its word and how many records it shows
  const filters: [RowFilter, string, number][] = [
    ["all", "All", counts.records],
    ["needs_action", "Needs action", counts.to_fix + counts.to_check],
    ["excluded", "Excluded", counts.excluded],
  ];
  return (
    <section className="summary-strip card" aria-label="Summary">
      <dl className="summary-strip__counts">
        <Count label="Records" value={counts.records} />
        <Count label="To fix" value={counts.open_errors} tone="red" />
        <Count label="Warnings" value={counts.open_warnings} tone="amber" />
        <Count label="Excluded" value={counts.excluded} />
      </dl>
      <div className="summary-strip__filters" role="group" aria-label="Show records">
        {filters.map(([value, word, count]) => (
          <button
            key={value}
            type="button"
            className="summary-strip__filter"
            aria-pressed={filter === value}
            onClick={() => onFilter(value)}
          >
            {word} {count}
          </button>
        ))}
      </div>
    </section>
  );
}

/** One count with its label; red and amber counts get their icon. */
function Count({ label, value, tone }: { label: string; value: number; tone?: "red" | "amber" }) {
  return (
    <div className="summary-strip__count">
      <dt>{label}</dt>
      <dd className={tone !== undefined ? `summary-strip__value--${tone}` : undefined}>
        {tone === "red" && <Icon name="cross-circle" size={18} strokeWidth={2} />}
        {tone === "amber" && <Icon name="warning" size={18} strokeWidth={2} />}
        {value}
      </dd>
    </div>
  );
}

// The action component of the selected issue (UI_SPEC §4.3 issue table): one view per action
// kind, all editing one ActionState that buildChoice turns into a change. Exclude record and
// bulk "also apply" come through extension slots; the duplicate comparison sits above (ResolutionPanel).
import type { ReactNode } from "react";
import type { CellAlternative, IssueSummary, ReviewCell, RunField } from "../../api/types";
import type { ActionKind, ActionOption, ActionState } from "../../lib/issueActions";
import { needsDocumentsCheck } from "../../lib/issueActions";
import { formatShortLocation } from "../../lib/sourceLocation";
import { Icon } from "../Icon";
import { ValueInput } from "./ValueInput";
import "./IssueActions.css";

/** Props shared by every action view. */
export interface IssueActionProps {
  kind: ActionKind | null;
  acceptLabel: string;
  issue: IssueSummary | null;
  cell: ReviewCell | null;
  field: RunField | null;
  state: ActionState;
  isSourceViewed: boolean;
  hasSources: boolean;
  isRunIssue: boolean;
  onState: (patch: Partial<ActionState>) => void;
  onViewSource: () => void;
  onShowAlternativeSource: (alternative: CellAlternative) => void;
  // M13: bulk "Also apply to N similar", Exclude record and the like, shown under the actions
  extraActions?: ReactNode;
}

/** One radio option: its value, its label, and why it is disabled (if it is). */
interface OptionItem {
  option: ActionOption;
  label: string;
  disabledReason?: string | null;
}

/** Return true when the user may change the field's value in the tool (extracted fields only). */
export function isEditableField(field: RunField | null): boolean {
  return field !== null && field.role === "extracted";
}

/** Show the action view for the selected issue (or the "Change value" view without one). */
export function IssueAction(props: IssueActionProps) {
  const { kind, issue } = props;
  // A clicked value without an issue: change it with a reason
  if (issue === null) {
    return <ChangeValueAction {...props} />;
  }
  if (issue.status !== "open") {
    return <p className="issue-action__note">This warning was accepted. Nothing more to do.</p>;
  }
  return (
    <div className="issue-action">
      {props.hasSources && <ViewSourceButton {...props} />}
      {kind === "enter_value" && <ValueField {...props} />}
      {kind === "pick_alternative" && <AlternativesAction {...props} />}
      {kind === "nothing_to_do" && <p className="issue-action__note">Nothing to do. This is shown for information.</p>}
      {kind !== null && kind !== "enter_value" && kind !== "pick_alternative" && kind !== "nothing_to_do" && (
        <OptionsAction {...props} />
      )}
      {props.extraActions}
    </div>
  );
}

/** "View source": opens the cited passage; marked once opened (needed for some accepts). */
function ViewSourceButton({ issue, isSourceViewed, onViewSource }: IssueActionProps) {
  return (
    <div className="issue-action__source">
      <button type="button" className="button-secondary" onClick={onViewSource}>
        <Icon name="eye" size={16} /> View source
      </button>
      {issue?.individual_review && (
        <span className={isSourceViewed ? "issue-action__viewed" : "muted"}>
          {isSourceViewed ? "Source opened" : "Open the source before you accept."}
        </span>
      )}
    </div>
  );
}

/** The value input of the field, ordered by the value as written (closest first). */
function ValueField({ field, cell, state, onState, label }: IssueActionProps & { label?: string }) {
  if (field === null) {
    return <p className="issue-action__note">This issue has no field to change.</p>;
  }
  return (
    <ValueInput
      field={field}
      value={state.value}
      hint={cell?.written_value ?? cell?.value ?? null}
      label={label}
      onChange={(value, problem) => onState({ value, valueProblem: problem })}
    />
  );
}

/** A value without an issue: enter the new value and a reason (required by the API). */
function ChangeValueAction(props: IssueActionProps) {
  if (!isEditableField(props.field)) {
    return <p className="issue-action__note">This value is not changed in the tool.</p>;
  }
  return (
    <div className="issue-action">
      <p className="issue-action__note">This value has no issue. To change it, enter the new value and a reason.</p>
      {props.hasSources && <ViewSourceButton {...props} />}
      <ValueField {...props} label="New value" />
      <TextArea label="Reason for the change (required)" value={props.state.reason} onChange={(reason) => props.onState({ reason })} />
    </div>
  );
}

/** Conflicting values: one radio per alternative (with "Show source"), or "Other value". */
function AlternativesAction(props: IssueActionProps) {
  const { cell, state, onState, onShowAlternativeSource } = props;
  const alternatives = cell?.alternatives ?? [];
  return (
    <fieldset className="issue-action__options">
      <legend className="issue-action__legend">Choose one value</legend>
      {alternatives.map((alternative) => (
        <label key={alternative.index} className="issue-action__option issue-action__option--card">
          <input
            type="radio"
            name="issue-option"
            checked={state.option === "alternative" && state.alternativeIndex === alternative.index}
            onChange={() => onState({ option: "alternative", alternativeIndex: alternative.index })}
          />
          <span className="issue-action__option-body">
            <strong>{alternative.value}</strong>
            <span className="muted">
              {alternative.sources[0] !== undefined ? formatShortLocation(alternative.sources[0].location) : "No source recorded"}
              {alternative.sources.length > 0 && (
                <>
                  {" · "}
                  <button type="button" className="button-text" onClick={() => onShowAlternativeSource(alternative)}>
                    Show source
                  </button>
                </>
              )}
            </span>
          </span>
        </label>
      ))}
      <RadioOption item={{ option: "other_value", label: "Other value" }} state={state} onState={onState} />
      {state.option === "other_value" && <ValueField {...props} />}
    </fieldset>
  );
}

/** Return the options an action kind offers, in UI_SPEC order. */
function listOptions(props: IssueActionProps): OptionItem[] {
  const { kind, acceptLabel, issue, field, isSourceViewed, isRunIssue, state } = props;
  const isEditable = isEditableField(field);
  const items: OptionItem[] = [];
  if (kind === "optional_not_found") {
    items.push({ option: "leave_blank", label: "Leave blank" });
  }
  // Only warnings can be accepted; individual-review ones after the source was opened (or,
  // for a run issue without sources, after the user confirms they checked the documents)
  if (issue !== null && issue.severity === "warning" && kind !== "optional_not_found") {
    const isManualCheck = needsDocumentsCheck(issue, isRunIssue);
    const isViewed = isManualCheck ? state.hasCheckedDocuments : isSourceViewed;
    const needsSource = issue.individual_review && !isViewed;
    const reason = isManualCheck ? "Confirm you checked the documents first." : "Open the source first.";
    items.push({ option: "accept", label: acceptLabel, disabledReason: needsSource ? reason : null });
  }
  const canChange = kind === "review_source" || kind === "accept_or_change" || kind === "optional_not_found";
  if (isEditable && canChange) {
    items.push({ option: "change", label: kind === "optional_not_found" ? "Add value" : "Change" });
  }
  if (isEditable && kind === "review_source") {
    items.push({ option: "not_found", label: "Mark not found" });
  }
  return items;
}

/** Accept / Change / Mark not found / Leave blank options, with the inputs they need. */
function OptionsAction(props: IssueActionProps) {
  const { issue, state, onState, isRunIssue } = props;
  const items = listOptions(props);
  const isNoteRequired = issue?.note_required === true;
  const isNoteShown = state.option === "accept" && (issue?.individual_review === true || isNoteRequired);
  return (
    <div className="issue-action__group">
      {issue !== null && needsDocumentsCheck(issue, isRunIssue) && (
        <DocumentsCheck state={state} onState={onState} />
      )}
      <fieldset className="issue-action__options">
        <legend className="issue-action__legend">What do you want to do?</legend>
        {items.map((item) => (
          <RadioOption key={item.option} item={item} state={state} onState={onState} />
        ))}
        {items.length === 0 && <p className="issue-action__note">This issue has no action here yet.</p>}
      </fieldset>
      {(state.option === "change" || state.option === "other_value") && <ValueField {...props} />}
      {isNoteShown && (
        <TextArea
          label={isNoteRequired ? "Note: what you did (required)" : "Note (optional)"}
          value={state.note}
          onChange={(note) => onState({ note })}
        />
      )}
    </div>
  );
}

/** A run issue that cites no passage: say so, and let the user confirm they checked the documents. */
function DocumentsCheck({ state, onState }: { state: ActionState; onState: (patch: Partial<ActionState>) => void }) {
  return (
    <>
      <p className="issue-action__note">No source passage was recorded for these items. Check the documents yourself, then say in the note what you did.</p>
      <label className="issue-action__check">
        <input type="checkbox" checked={state.hasCheckedDocuments} onChange={(event) => onState({ hasCheckedDocuments: event.target.checked })} />
        I checked the documents for these items
      </label>
    </>
  );
}

/** One radio button option; a disabled one says why. */
function RadioOption({ item, state, onState }: { item: OptionItem; state: ActionState; onState: (patch: Partial<ActionState>) => void }) {
  const isDisabled = item.disabledReason !== null && item.disabledReason !== undefined;
  return (
    <label className={`issue-action__option${isDisabled ? " issue-action__option--disabled" : ""}`}>
      <input
        type="radio"
        name="issue-option"
        checked={state.option === item.option}
        disabled={isDisabled}
        onChange={() => onState({ option: item.option })}
      />
      <span>
        {item.label}
        {isDisabled && <span className="muted"> ({item.disabledReason})</span>}
      </span>
    </label>
  );
}

/** A labelled multi-line text box (notes and reasons). */
function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="issue-action__text">
      <span className="dropdown__label">{label}</span>
      <textarea rows={2} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

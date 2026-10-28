// The processing step list (not a percentage bar): finished steps checked, current highlighted.
// Each step's state comes from the run status (see lib/processingSteps.ts).
import type { RunStatus } from "../api/types";
import { PROCESSING_STEPS, findStepState, type StepState } from "../lib/processingSteps";
import { Icon } from "./Icon";
import "./StepList.css";

// Words read out by screen readers for each state (the marker alone is only a shape)
const STATE_WORDS: Record<StepState, string> = {
  done: "done",
  current: "in progress",
  waiting: "not started",
};

/** Props of the list: the run status the steps are shown for. */
interface StepListProps {
  status: RunStatus;
}

/** Show the six processing steps with their state for a run status. */
export function StepList({ status }: StepListProps) {
  return (
    <ol className="step-list" aria-label="Processing steps">
      {PROCESSING_STEPS.map((step) => {
        const state = findStepState(step, status);
        return (
          <li
            key={step.label}
            className={`step-list__step step-list__step--${state}`}
            aria-current={state === "current" ? "step" : undefined}
            data-state={state}
          >
            <StepMarker state={state} />
            <div>
              <div className="step-list__label">
                {step.label}
                <span className="visually-hidden"> ({STATE_WORDS[state]})</span>
              </div>
              {state === "current" && <div className="step-list__detail">{step.detail}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Draw the round marker of a step: a check, a spinning ring or an empty ring. */
function StepMarker({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <span className="step-list__marker step-list__marker--done">
        <Icon name="check" size={16} strokeWidth={2.4} />
      </span>
    );
  }
  return <span className={`step-list__marker step-list__marker--${state}`} aria-hidden="true" />;
}

// The processing steps of UI_SPEC §4.2, one per run status, and how a status maps onto them.
import type { RunStatus } from "../api/types";

export type StepState = "done" | "current" | "waiting";

/** One step in the list: its label, a short detail line, and the statuses it covers. */
export interface ProcessingStep {
  label: string;
  detail: string;
  statuses: RunStatus[];
}

// Statuses in the order the processing flow goes through them
const PROCESSING_ORDER: RunStatus[] = [
  "created",
  "ingesting",
  "extracting",
  "verifying_extraction",
  "normalizing",
  "matching",
  "naming",
  "assembling",
  "validating",
];

// Statuses that mean processing has finished successfully
const FINISHED_STATUSES: RunStatus[] = ["in_review", "rechecking"];

export const PROCESSING_STEPS: ProcessingStep[] = [
  {
    label: "Reading documents",
    detail: "Reading each file and labeling its sections",
    statuses: ["created", "ingesting"],
  },
  {
    label: "Extracting consumables",
    detail: "Finding Consumable Types and their fields",
    statuses: ["extracting"],
  },
  {
    label: "Checking against the documents",
    detail: "Checking each value against the text it cites, then a second review",
    statuses: ["verifying_extraction"],
  },
  {
    label: "Formatting values",
    detail: "Cleaning values and matching them to the lookup lists",
    statuses: ["normalizing"],
  },
  {
    label: "Matching list values",
    detail: "Suggesting list values for text that matches none exactly",
    statuses: ["matching"],
  },
  {
    label: "Suggesting names",
    detail: "Suggesting a Consumable Type name for each record",
    statuses: ["naming"],
  },
  {
    label: "Filling derived fields",
    detail: "Working out Critical, Consumable Class and the other derived fields",
    statuses: ["assembling"],
  },
  {
    label: "Final checks",
    detail: "Running the checks and preparing the records for review",
    statuses: ["validating"],
  },
];

/** Return true while a run is still being processed (the screen keeps polling). */
export function isProcessing(status: RunStatus): boolean {
  return PROCESSING_ORDER.includes(status);
}

/** Return the state of one step for a run status: done, current or waiting. */
export function findStepState(step: ProcessingStep, status: RunStatus): StepState {
  // A finished run has every step done
  if (FINISHED_STATUSES.includes(status)) {
    return "done";
  }
  if (step.statuses.includes(status)) {
    return "current";
  }
  // A step is done once the run is past the last status it covers
  const position = PROCESSING_ORDER.indexOf(status);
  const lastStepPosition = Math.max(...step.statuses.map((s) => PROCESSING_ORDER.indexOf(s)));
  return position > lastStepPosition ? "done" : "waiting";
}

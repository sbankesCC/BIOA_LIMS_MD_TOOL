// Line icons copied from the mockups, drawn with the current text color.
// Icons are decoration: screen readers skip them, so a word must always sit next to one.

export type IconName =
  | "check"
  | "cross-circle"
  | "warning"
  | "clock"
  | "help"
  | "upload"
  | "file"
  | "close"
  | "arrow-right"
  | "save"
  | "refresh"
  | "eye";

// The SVG path data of each icon (24 x 24 view box)
const ICON_PATHS: Record<IconName, string[]> = {
  check: ["M5 12.5l4.5 4.5L19 7.5"],
  "cross-circle": ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M15 9l-6 6M9 9l6 6"],
  warning: ["M12 4 2.8 19.5h18.4z", "M12 10v4.5", "M12 17.5h.01"],
  clock: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7v5l3 2"],
  help: [
    "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z",
    "M9.5 9.2a2.6 2.6 0 0 1 5 .8c0 1.8-2.5 2.2-2.5 3.8",
    "M12 17h.01",
  ],
  upload: ["M12 15V4", "M7.5 8.5 12 4l4.5 4.5", "M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"],
  file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5"],
  close: ["M6 6l12 12M18 6 6 18"],
  "arrow-right": ["M5 12h14M13 6l6 6-6 6"],
  save: ["M5 4h11l3 3v13H5z", "M8 4v5h7V4", "M8 20v-6h8v6"],
  refresh: ["M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7"],
  eye: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z"],
};

/** Props of an icon: which one, its size in pixels and its stroke width. */
interface IconProps {
  name: IconName;
  size?: number;
  strokeWidth?: number;
}

/** Draw one line icon, hidden from screen readers. */
export function Icon({ name, size = 18, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      data-icon={name}
    >
      {ICON_PATHS[name].map((path) => (
        <path key={path} d={path} />
      ))}
    </svg>
  );
}

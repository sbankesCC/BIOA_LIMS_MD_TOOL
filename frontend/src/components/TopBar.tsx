// The top bar on every screen: product name, New run, Runs, How it works and Admin (UI_SPEC §3).
import { NavLink } from "react-router-dom";
import { Icon } from "./Icon";
import "./TopBar.css";

/** Props of the top bar: what "How it works" does, and whether to show Admin (hidden after a 403). */
interface TopBarProps {
  onOpenHowItWorks: () => void;
  isAdminShown: boolean;
}

/** Return the class of a main navigation link, marking the current page. */
function makeNavClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "top-bar__link top-bar__link--active" : "top-bar__link";
}

/** Return the class of the Admin button: filled white on the admin screens (mockup 4). */
function makeAdminClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "top-bar__admin top-bar__admin--active" : "top-bar__admin";
}

/** Show the blue top bar with the main navigation. */
export function TopBar({ onOpenHowItWorks, isAdminShown }: TopBarProps) {
  return (
    <header className="top-bar">
      <div className="top-bar__inner">
        {/* Left: product name and the main pages */}
        <div className="top-bar__left">
          <NavLink to="/" className="top-bar__brand">
            Consumable Type Extractor
          </NavLink>
          <nav aria-label="Main" className="top-bar__nav">
            <NavLink to="/" end className={makeNavClass}>
              New run
            </NavLink>
            <NavLink to="/runs" className={makeNavClass}>
              Runs
            </NavLink>
          </nav>
        </div>
        {/* Right: help popup and Admin (shown unless the API refused an admin call with 403) */}
        <div className="top-bar__right">
          <button type="button" className="top-bar__help" onClick={onOpenHowItWorks}>
            <Icon name="help" />
            How it works
          </button>
          {isAdminShown && (
            <NavLink to="/admin" className={makeAdminClass}>
              Admin
            </NavLink>
          )}
        </div>
      </div>
    </header>
  );
}

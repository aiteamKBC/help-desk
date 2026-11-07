import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import "./SupportMasterHeader.css";

/** Pill class for links rendered inside the header's action slot. */
export const supportMasterHeaderPillClassName = "support-master-header__pill";

const defaultActions = (
  <Link to="/admin" className={supportMasterHeaderPillClassName}>
    <ShieldCheck aria-hidden="true" />
    <span>Admin</span>
  </Link>
);

/**
 * The approved Kent Business College horizontal header (campus photo + crest,
 * purple gradient, lavender wave). `actions` replaces the default Admin button
 * with route-specific navigation; everything else is shared.
 *
 * `variant="banner"` (admin dashboard and Knowledge Base) renders the approved
 * header artwork instead of the composed photo, gradient and wave.
 */
export const SupportMasterHeader = ({
  actions = defaultActions,
  variant = "photo",
}: {
  actions?: ReactNode;
  variant?: "photo" | "banner";
}) => variant === "banner" ? (
  <header className="support-master-header support-master-header--banner" aria-label="Kent Business College">
    <img
      src="/kbc-dashboard-header.jpg"
      alt="Kent Business College campus building with the college crest"
      className="support-master-header__banner"
      draggable={false}
    />
    {actions ? <nav className="support-master-header__actions">{actions}</nav> : null}
  </header>
) : (
  <header className="support-master-header" aria-label="Kent Business College">
    <div className="support-master-header__photo" aria-hidden="true" />
    <div className="support-master-header__tint" aria-hidden="true" />

    {actions ? <nav className="support-master-header__actions">{actions}</nav> : null}

    <svg
      className="support-master-header__wave"
      viewBox="0 0 1440 52"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        className="support-master-header__wave-back"
        d="M0 4C238 46 514 36 720 38C1006 42 1248 26 1440 6V52H0Z"
      />
      <path
        className="support-master-header__wave-gold"
        d="M0 4C238 46 514 36 720 38C1006 42 1248 26 1440 6"
      />
      <path
        className="support-master-header__wave-front"
        d="M0 16C238 52 516 44 720 46C1008 49 1252 38 1440 20V52H0Z"
      />
    </svg>
  </header>
);

import { Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import "./SupportMasterHeader.css";

export const SupportMasterHeader = () => (
  <header className="support-master-header" aria-label="Kent Business College">
    <div className="support-master-header__photo" aria-hidden="true" />
    <div className="support-master-header__tint" aria-hidden="true" />

    <Link to="/admin" className="support-master-header__admin">
      <ShieldCheck aria-hidden="true" />
      <span>Admin</span>
    </Link>

    <svg
      className="support-master-header__wave"
      viewBox="0 0 1440 52"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M0 4C238 46 514 36 720 38C1006 42 1248 26 1440 6V52H0Z"
        fill="rgba(212,198,255,0.9)"
      />
      <path
        d="M0 16C238 52 516 44 720 46C1008 49 1252 38 1440 20V52H0Z"
        fill="#EEEAFD"
      />
    </svg>
  </header>
);

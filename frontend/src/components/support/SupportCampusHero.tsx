import type { ReactNode } from "react";

/**
 * The approved split-screen campus panel: Kent Business College photo clipped
 * by the purple / lavender S-wave, plus the white hero copy. Shared by the
 * Support Request entry page and Admin Login; layout styles live in
 * EmailVerification.css under `.support-landing`.
 */
export const SupportCampusHero = ({ title, subtitle }: { title: ReactNode; subtitle: ReactNode }) => (
  <aside className="support-hero" aria-label="Kent Business College">
    <div className="support-hero-wave" aria-hidden="true">
      <svg
        className="support-wave-ribbons"
        viewBox="0 0 1712 913"
        preserveAspectRatio="none"
        focusable="false"
      >
        <defs>
          <clipPath id="support-campus-clip" clipPathUnits="userSpaceOnUse">
            <path d="M0 0H665C718 68 751 151 749 233C746 361 705 482 644 596C578 719 475 820 342 873C253 909 167 913 82 913H0Z" />
          </clipPath>
          <linearGradient id="support-purple-ribbon" gradientUnits="userSpaceOnUse" x1="490" y1="120" x2="415" y2="913">
            <stop offset="0" stopColor="#5310ff" />
            <stop offset="0.52" stopColor="#4810f2" />
            <stop offset="1" stopColor="#5a00f5" />
          </linearGradient>
          <linearGradient id="support-lavender-ribbon" gradientUnits="userSpaceOnUse" x1="470" y1="913" x2="810" y2="65">
            <stop offset="0" stopColor="#5c18f4" />
            <stop offset="0.52" stopColor="#9a74f7" />
            <stop offset="1" stopColor="#c8b5fb" />
          </linearGradient>
          <linearGradient id="support-lavender-soft" gradientUnits="userSpaceOnUse" x1="560" y1="850" x2="860" y2="90">
            <stop offset="0" stopColor="#cbb2fa" stopOpacity="0.9" />
            <stop offset="1" stopColor="#e9e1fd" stopOpacity="0.72" />
          </linearGradient>
          <linearGradient id="support-photo-shade" gradientUnits="userSpaceOnUse" x1="0" y1="330" x2="0" y2="913">
            <stop offset="0.12" stopColor="#2410a8" stopOpacity="0" />
            <stop offset="0.58" stopColor="#2710b6" stopOpacity="0.23" />
            <stop offset="1" stopColor="#25108f" stopOpacity="0.48" />
          </linearGradient>
        </defs>
        <path
          className="support-wave-corner-band"
          d="M1270 0C1325 85 1425 140 1550 172C1635 194 1690 245 1712 310V0Z"
          fill="#e8dfff"
          fillOpacity="0.55"
        />
        <path
          className="support-wave-corner"
          d="M1300 0C1350 70 1440 120 1560 150C1640 170 1690 215 1712 270V0Z"
          fill="#fbfaff"
          fillOpacity="0.85"
        />
        <path
          className="support-wave-layer support-wave-layer-soft"
          d="M0 0H850C816 75 804 159 801 248C796 386 767 506 719 621C674 727 634 817 647 866C653 887 664 902 680 913H0Z"
          fill="url(#support-lavender-soft)"
        />
        <path
          className="support-wave-layer support-wave-layer-lavender"
          d="M0 0H793C777 74 775 155 771 240C765 370 733 490 679 607C628 718 574 811 559 863C553 883 554 900 562 913H0Z"
          fill="url(#support-lavender-ribbon)"
        />
        <path
          className="support-wave-layer support-wave-layer-purple"
          d="M0 0H690C741 70 770 153 766 239C760 369 716 492 651 607C579 733 487 831 390 874C370 884 353 897 343 913H0Z"
          fill="url(#support-purple-ribbon)"
        />
        <g className="support-wave-photo" clipPath="url(#support-campus-clip)">
          <image
            href="/support-campus.png"
            x="-32"
            y="-12"
            width="790"
            height="925"
            preserveAspectRatio="xMidYMin slice"
          />
          <rect width="790" height="913" fill="url(#support-photo-shade)" />
        </g>
      </svg>
    </div>
    <div className="support-hero-copy">
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </div>
  </aside>
);

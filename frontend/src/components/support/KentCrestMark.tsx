import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const officialKentWordmarkSrc = "https://kentbusinesscollege.com/wp-content/uploads/2025/12/Kent-Business-College-e1768393206822.png";
const localKentWordmarkFallbackSrc = "/kent-business-college-mark.svg";
const localKentCrestSrc = "/kent-crest.svg";

type KentCrestMarkProps = {
  className?: string;
  imageClassName?: string;
  alt?: string;
  src?: string;
  variant?: "full" | "crest";
  frame?: "card" | "plain";
};

export const KentCrestMark = ({
  className,
  imageClassName,
  alt = "Kent Business College logo",
  src,
  variant = "full",
  frame = "card",
}: KentCrestMarkProps) => {
  const resolvedSrc = src || (variant === "crest" ? localKentCrestSrc : officialKentWordmarkSrc);
  const fallbackSrc = variant === "crest" ? localKentCrestSrc : localKentWordmarkFallbackSrc;
  const [currentSrc, setCurrentSrc] = useState(resolvedSrc);

  useEffect(() => {
    setCurrentSrc(resolvedSrc);
  }, [resolvedSrc]);

  return (
    <div
      className={cn(
        "overflow-hidden",
        frame === "plain"
          ? "border-transparent bg-transparent shadow-none ring-0"
          : variant === "crest"
            ? "flex items-center justify-center border border-primary/12 bg-white/95 ring-1 ring-primary/5 shadow-soft"
            : "border border-primary/10 bg-white/95 ring-1 ring-primary/5 shadow-card",
        className,
      )}
    >
      <img
        src={currentSrc}
        alt={alt}
        onError={() => {
          if (currentSrc !== fallbackSrc) {
            setCurrentSrc(fallbackSrc);
          }
        }}
        className={cn(
          "h-full w-full object-contain",
          frame === "plain" ? "p-0" : variant === "crest" ? "p-2.5" : "p-3",
          imageClassName,
        )}
      />
    </div>
  );
};

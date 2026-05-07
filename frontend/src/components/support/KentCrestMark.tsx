import { cn } from "@/lib/utils";

type KentCrestMarkProps = {
  className?: string;
  imageClassName?: string;
  alt?: string;
  src?: string;
};

export const KentCrestMark = ({
  className,
  imageClassName,
  alt = "Kent Business College logo",
  src = "/kent-business-college-mark.svg",
}: KentCrestMarkProps) => (
  <div
    className={cn(
      "overflow-hidden border border-primary/10 bg-white/95 shadow-card ring-1 ring-primary/5",
      className,
    )}
  >
    <img
      src={src}
      alt={alt}
      className={cn("h-full w-full object-contain p-2", imageClassName)}
    />
  </div>
);

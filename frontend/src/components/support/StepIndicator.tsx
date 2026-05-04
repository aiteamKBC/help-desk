import { Check } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useSupport } from "@/context/SupportContext";
import { cn } from "@/lib/utils";

const steps = [
  { label: "Email", path: "/" },
  { label: "Inquiry", path: "/support/inquiry" },
  { label: "Chat", path: "/support/chat" },
  { label: "Status", path: "/support/status" },
];

export const StepIndicator = ({ current }: { current: number }) => {
  const navigate = useNavigate();
  const { ticket } = useSupport();

  const isStepAvailable = (stepIndex: number) => {
    if (stepIndex > current) {
      return false;
    }

    if (stepIndex === 1) {
      return true;
    }

    if (stepIndex === 2) {
      return Boolean(ticket.email);
    }

    if (stepIndex === 3) {
      return Boolean(ticket.id);
    }

    if (stepIndex === 4) {
      return Boolean(ticket.id);
    }

    return false;
  };

  return (
    <div className="w-full max-w-3xl mx-auto mb-8">
      <div className="flex items-center justify-between">
        {steps.map((step, i) => {
          const idx = i + 1;
          const isDone = idx < current;
          const isActive = idx === current;
          const isClickable = isStepAvailable(idx) && !isActive;
          return (
            <div key={step.label} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (isClickable) {
                      navigate(step.path);
                    }
                  }}
                  disabled={!isClickable}
                  className={cn(
                    "h-9 w-9 rounded-full flex items-center justify-center text-sm font-semibold border transition-all",
                    isDone && "bg-success border-success text-success-foreground",
                    isActive && "gradient-primary border-transparent text-primary-foreground shadow-card",
                    !isDone && !isActive && "bg-card border-border text-muted-foreground",
                    isClickable && "cursor-pointer hover:scale-105",
                    !isClickable && "cursor-default"
                  )}
                >
                  {isDone ? <Check className="h-4 w-4" /> : idx}
                </button>
                <span
                  className={cn(
                    "text-xs font-medium hidden sm:block",
                    isActive ? "text-foreground" : "text-muted-foreground",
                    isClickable && "cursor-pointer"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div className={cn("h-0.5 flex-1 mx-2 sm:mx-3 mb-6 rounded-full", idx < current ? "bg-success" : "bg-border")} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

import { Check } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useSupport } from "@/context/SupportContext";
import { canReturnToChat, isQuickTicketOnlyRequesterRole, shouldShowStatusStep } from "@/lib/supportFlow";
import { cn } from "@/lib/utils";

const defaultSteps = [
  { label: "Email", path: "/", number: 1 },
  { label: "Inquiry", path: "/support/inquiry", number: 2 },
  { label: "Chat", path: "/support/chat", number: 3 },
  { label: "Status", path: "/support/status", number: 4 },
];

const coachSteps = [
  { label: "Email", path: "/", number: 1 },
  { label: "Inquiry", path: "/support/inquiry", number: 2 },
  { label: "Options", path: "/support/options", number: 3 },
  { label: "Status", path: "/support/status", number: 4 },
];

export const StepIndicator = ({ current }: { current: number }) => {
  const navigate = useNavigate();
  const { ticket, bookingSummary } = useSupport();
  const quickTicketOnlyFlow = isQuickTicketOnlyRequesterRole(ticket.requesterRole);
  const steps = quickTicketOnlyFlow ? coachSteps : defaultSteps;
  const chatStepAvailable = canReturnToChat(ticket);
  const normalizedCurrent = Math.min(Math.max(current, 1), steps.length);
  const isInterimStep = !Number.isInteger(current);
  const furthestStepReached = (() => {
    if (shouldShowStatusStep(ticket, bookingSummary)) {
      return 4;
    }

    if (quickTicketOnlyFlow) {
      return ticket.id ? 3 : ticket.email ? 2 : 1;
    }

    if (ticket.id) {
      return 3;
    }

    if (ticket.email) {
      return 2;
    }

    return 1;
  })();

  const isStepAvailable = (stepIndex: number) => {
    if (!quickTicketOnlyFlow && stepIndex === 3 && !chatStepAvailable) {
      return false;
    }

    return stepIndex <= furthestStepReached;
  };

  return (
    <div className="mx-auto mb-6 w-full max-w-3xl sm:mb-8">
      <div className="flex items-center justify-between">
        {steps.map((step, i) => {
          const idx = i + 1;
          const isCompleted = idx < normalizedCurrent;
          const isActive = !isInterimStep && idx === normalizedCurrent;
          const isReached = idx <= furthestStepReached;
          const isClickable = isStepAvailable(idx) && !isActive;
          const connectorProgress = Math.max(0, Math.min(1, normalizedCurrent - idx));
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
                    "flex h-10 w-10 items-center justify-center rounded-full border text-[13px] font-semibold transition-all sm:h-9 sm:w-9 sm:text-sm",
                    isCompleted && "border-primary bg-primary text-primary-foreground shadow-soft",
                    isActive && "border-primary bg-primary text-primary-foreground ring-4 ring-primary/15 shadow-card scale-[1.03]",
                    !isCompleted && !isActive && !isReached && "bg-card border-border text-muted-foreground",
                    !isCompleted && !isActive && isReached && "border-primary/25 bg-primary/5 text-primary/80",
                    isClickable && "cursor-pointer hover:scale-105 hover:border-primary hover:bg-primary/10",
                    !isClickable && "cursor-default"
                  )}
                >
                  {isCompleted ? <Check className="h-4 w-4" /> : step.number}
                </button>
                <span
                  className={cn(
                    "text-[10px] font-medium tracking-[0.01em] sm:text-xs",
                    isCompleted && "text-primary",
                    isActive && "text-primary",
                    !isCompleted && !isActive && isReached && "text-foreground/80",
                    !isReached && "text-muted-foreground",
                    isClickable && "cursor-pointer"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div className="relative mb-7 mx-1.5 h-0.5 flex-1 overflow-hidden rounded-full bg-border sm:mx-3 sm:mb-6">
                  <div
                    className={cn(
                      "absolute inset-y-0 left-0 rounded-full bg-primary transition-all",
                      connectorProgress > 0 && connectorProgress < 1 && "bg-primary/60",
                    )}
                    style={{ width: `${connectorProgress * 100}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

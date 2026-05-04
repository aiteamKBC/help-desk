import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, AlertTriangle, ArrowRight, LifeBuoy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import { useSupport } from "@/context/SupportContext";

const isValidEmailFormat = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

const EmailVerification = () => {
  const navigate = useNavigate();
  const { ticket, setTicket, updateTicket } = useSupport();
  const [email, setEmail] = useState(ticket.email);
  const [errorTitle, setErrorTitle] = useState("Invalid Email");
  const [errorMessage, setErrorMessage] = useState("Please enter a valid email address.");
  const [errorOpen, setErrorOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleNext = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();

    if (!isValidEmailFormat(trimmedEmail)) {
      setErrorTitle("Invalid Email");
      setErrorMessage("Please enter a valid email address.");
      setErrorOpen(true);
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch("/api/verify-email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: trimmedEmail }),
      });

      const payload = (await response.json().catch(() => null)) as
        | { exists?: boolean; message?: string }
        | null;

      if (response.ok && payload?.exists) {
        if (ticket.email && ticket.email !== trimmedEmail) {
          setTicket({
            id: "",
            email: trimmedEmail,
            category: "",
            technicalSubcategory: "",
            inquiry: "",
            evidence: [],
            status: "Open",
            assignedTeam: "Unassigned",
            slaStatus: "Pending Review",
            createdAt: "",
            chatHistory: [],
          });
        } else {
          updateTicket({ email: trimmedEmail });
        }
        navigate("/support/inquiry");
        return;
      }

      setErrorTitle(response.status === 400 ? "Invalid Email" : "Email Not Found");
      setErrorMessage(payload?.message || "This email is not registered in our records.");
      setErrorOpen(true);
    } catch {
      setErrorTitle("Verification Unavailable");
      setErrorMessage("We could not verify your email right now. Please try again.");
      setErrorOpen(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SupportLayout>
      <StepIndicator current={1} />
      <div className="max-w-md mx-auto">
        <div className="bg-card rounded-2xl border shadow-card p-8">
          <div className="flex justify-center mb-5">
            <div className="h-14 w-14 rounded-2xl gradient-primary flex items-center justify-center shadow-card">
              <LifeBuoy className="h-7 w-7 text-primary-foreground" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-center mb-2">Support Request</h1>
          <p className="text-sm text-muted-foreground text-center mb-7">
            Please enter the email address registered in our database to continue.
          </p>
          <form onSubmit={handleNext} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email">Registered Email</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  placeholder="Enter your registered email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-9 h-11"
                  autoFocus
                  required
                />
              </div>
            </div>
            <Button
              type="submit"
              className="w-full h-11 gradient-primary border-0"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Checking..." : "Next"}
              {!isSubmitting && <ArrowRight className="ml-2 h-4 w-4" />}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground text-center mt-6">
            Use the same email address stored for you in KBC records.
          </p>
        </div>
      </div>

      <Dialog open={errorOpen} onOpenChange={setErrorOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <div className="mx-auto h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center mb-2">
              <AlertTriangle className="h-6 w-6 text-destructive" />
            </div>
            <DialogTitle className="text-center">{errorTitle}</DialogTitle>
            <DialogDescription className="text-center">
              {errorMessage}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button className="w-full" onClick={() => setErrorOpen(false)}>
              Try Again
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default EmailVerification;

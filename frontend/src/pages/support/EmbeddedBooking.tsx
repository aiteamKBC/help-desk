import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ExternalLink, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import { useSupport } from "@/context/SupportContext";

interface BookingContextResponse {
  bookingUrl: string;
  learner: {
    id: number;
    fullName: string;
    email: string;
    phone: string;
  };
  ticket: {
    id: string;
    category: string;
    technicalSubcategory: string;
    inquiry: string;
    status: string;
  };
  prefill: {
    fullName: string;
    email: string;
    phone: string;
    specialRequests: string;
  };
}

const EmbeddedBooking = () => {
  const navigate = useNavigate();
  const { ticket } = useSupport();
  const [bookingContext, setBookingContext] = useState<BookingContextResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!ticket.id) {
      navigate("/support/chat");
      return;
    }

    const abortController = new AbortController();

    const loadBookingContext = async () => {
      setIsLoading(true);
      setErrorMessage("");

      try {
        const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/booking-context`, {
          signal: abortController.signal,
        });

        const payload = (await response.json().catch(() => null)) as
          | (BookingContextResponse & { message?: string })
          | { message?: string }
          | null;

        if (!response.ok || !payload || !("bookingUrl" in payload)) {
          setErrorMessage(payload?.message || "We could not prepare the booking page right now.");
          return;
        }

        setBookingContext(payload);
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setErrorMessage("We could not connect to the booking service right now.");
        }
      } finally {
        setIsLoading(false);
      }
    };

    void loadBookingContext();

    return () => abortController.abort();
  }, [navigate, ticket.id]);

  return (
    <SupportLayout>
      <StepIndicator current={3} />
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Booking Stage</h1>
            <p className="text-sm text-muted-foreground">
              Review the learner details below, then continue to the official booking page to complete the session request.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => navigate("/support/chat")}>
              <ArrowLeft className="mr-2 h-4 w-4" /> Back to Chat
            </Button>
            {bookingContext?.bookingUrl && (
              <Button
                className="border-0 gradient-primary"
                onClick={() => window.open(bookingContext.bookingUrl, "_blank", "noopener,noreferrer")}
              >
                Open Booking Page
                <ExternalLink className="ml-2 h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {isLoading && (
          <div className="flex min-h-64 items-center justify-center rounded-2xl border bg-card shadow-card">
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <LoaderCircle className="h-5 w-5 animate-spin" />
              Preparing booking details...
            </div>
          </div>
        )}

        {!isLoading && errorMessage && (
          <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-5 shadow-card">
            <div className="font-semibold text-foreground">Booking page unavailable</div>
            <p className="mt-1 text-sm text-muted-foreground">{errorMessage}</p>
          </div>
        )}

        {!isLoading && bookingContext && (
          <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
            <aside className="space-y-4 rounded-2xl border bg-card p-5 shadow-card">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Booking Guidance
                </div>
                <p className="mt-2 text-sm leading-6 text-foreground">
                  Use the official booking page to choose the session slot that suits you. The learner and ticket details
                  shown here are provided for reference while you complete the booking.
                </p>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  If the external page asks for the same information again, use the details listed in this panel.
                </p>
              </div>

              <section className="rounded-xl border bg-secondary/20 p-4">
                <div className="text-sm font-semibold">Learner Details</div>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Name</dt>
                    <dd className="font-medium">{bookingContext.learner.fullName || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Email</dt>
                    <dd className="font-medium break-all">{bookingContext.learner.email}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Phone</dt>
                    <dd className="font-medium">{bookingContext.learner.phone || "-"}</dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-xl border bg-secondary/20 p-4">
                <div className="text-sm font-semibold">Ticket Context</div>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Ticket</dt>
                    <dd className="font-medium">{bookingContext.ticket.id}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Category</dt>
                    <dd className="font-medium">{bookingContext.ticket.category}</dd>
                  </div>
                  {bookingContext.ticket.technicalSubcategory && (
                    <div>
                      <dt className="text-muted-foreground">Technical Subcategory</dt>
                      <dd className="font-medium">{bookingContext.ticket.technicalSubcategory}</dd>
                    </div>
                  )}
                  <div>
                    <dt className="text-muted-foreground">Special Requests</dt>
                    <dd className="font-medium whitespace-pre-wrap">{bookingContext.prefill.specialRequests || "-"}</dd>
                  </div>
                </dl>
              </section>
            </aside>

            <section className="rounded-2xl border bg-card p-6 shadow-card">
              <div className="text-lg font-semibold text-foreground">Continue to Outlook Bookings</div>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                The booking page opens directly on the official Outlook Bookings site so you can complete the request
                without relying on an embedded frame.
              </p>
              <div className="mt-6 rounded-xl border bg-secondary/20 p-4">
                <div className="text-sm font-medium text-foreground">Booking URL</div>
                <div className="mt-2 break-all text-sm text-muted-foreground">{bookingContext.bookingUrl}</div>
              </div>
              <div className="mt-6 flex flex-wrap gap-3">
                <Button
                  className="border-0 gradient-primary"
                  onClick={() => window.open(bookingContext.bookingUrl, "_blank", "noopener,noreferrer")}
                >
                  Open Booking Page
                  <ExternalLink className="ml-2 h-4 w-4" />
                </Button>
                <Button variant="outline" onClick={() => navigate("/support/chat")}>
                  <ArrowLeft className="mr-2 h-4 w-4" /> Return to Chat
                </Button>
              </div>
            </section>
          </div>
        )}
      </div>
    </SupportLayout>
  );
};

export default EmbeddedBooking;

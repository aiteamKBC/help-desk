import { CalendarCheck, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "@/components/support/StepIndicator";
import { SupportLayout } from "@/components/support/SupportLayout";

const dummyMeetingLink = "https://meet.kentcollege.example/support-session";

const BookingConfirmed = () => (
  <SupportLayout>
    <StepIndicator current={4} />
    <main className="max-w-5xl mx-auto">
      <section className="px-6 py-10 text-center border bg-card rounded-2xl shadow-card md:px-10">
        <div className="flex items-center justify-center w-16 h-16 mx-auto mb-5 rounded-2xl bg-success/10 text-success">
          <CalendarCheck className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-semibold tracking-normal text-foreground md:text-3xl">
          Thank you for reaching Kent College Support
        </h1>
        <p className="max-w-3xl mx-auto mt-3 text-base leading-7 text-muted-foreground">
          The meeting have been scheduled and a support agent has been notified. You can reach the meeting through the link below or via the link sent to your E-mail
        </p>
        <Button asChild className="mt-7 border-0 gradient-primary">
          <a href={dummyMeetingLink} target="_blank" rel="noreferrer">
            Meeting Link
            <ExternalLink className="w-4 h-4 ml-2" />
          </a>
        </Button>
      </section>
    </main>
  </SupportLayout>
);

export default BookingConfirmed;

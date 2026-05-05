import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, MessageSquare, ArrowLeft, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import { useSupport } from "@/context/SupportContext";
import { downloadChatPdf } from "@/lib/chatPdf";
import { toast } from "sonner";

const TicketStatus = () => {
  const navigate = useNavigate();
  const { ticket } = useSupport();
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownloadPdf = async () => {
    if (ticket.chatHistory.length === 0) {
      toast.error("No chat history is available to export yet.");
      return;
    }

    setIsDownloading(true);

    try {
      await downloadChatPdf({
        ticketId: ticket.id || "support-chat",
        messages: ticket.chatHistory,
      });
    } catch {
      toast.error("We could not generate the PDF right now.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <SupportLayout>
      <StepIndicator current={4} />
      <div className="max-w-3xl mx-auto">
        <div className="bg-card rounded-2xl border shadow-card p-8 text-center">
          <div className="mx-auto h-14 w-14 rounded-full bg-success/10 flex items-center justify-center mb-3">
            <CheckCircle2 className="h-7 w-7 text-success" />
          </div>
          <h1 className="text-2xl font-bold mb-2">Resolution Confirmed</h1>
          <p className="text-sm leading-6 text-muted-foreground max-w-xl mx-auto">
            Thank you for contacting Kent College Support. It was a pleasure assisting you today. We appreciate your time and look forward to supporting you again in the future.
          </p>
        </div>

        <div className="flex flex-wrap gap-3 justify-center mt-6">
          <Button variant="outline" onClick={() => navigate("/")}>
            <ArrowLeft className="h-4 w-4 mr-2" /> Back to Dashboard
          </Button>
          <Button onClick={() => navigate("/support/chat")} className="gradient-primary border-0">
            <MessageSquare className="h-4 w-4 mr-2" /> Open Chat Again
          </Button>
          <Button variant="outline" onClick={() => void handleDownloadPdf()} disabled={isDownloading}>
            <Download className="h-4 w-4 mr-2" /> {isDownloading ? "Preparing PDF..." : "Download Chat PDF"}
          </Button>
        </div>
      </div>
    </SupportLayout>
  );
};

export default TicketStatus;

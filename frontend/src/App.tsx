import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SupportProvider } from "@/context/SupportContext";
import NotFound from "./pages/NotFound.tsx";
import EmailVerification from "./pages/support/EmailVerification.tsx";
import InquiryDetails from "./pages/support/InquiryDetails.tsx";
import ChatSupport from "./pages/support/ChatSupport.tsx";
import TicketStatus from "./pages/support/TicketStatus.tsx";
import Documentation from "./pages/support/Documentation.tsx";
import AgentDashboard from "./pages/support/AgentDashboard.tsx";
import AdminLogin from "./pages/support/AdminLogin.tsx";
import { RequireAdmin } from "./components/support/RequireAdmin.tsx";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <SupportProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<EmailVerification />} />
            <Route path="/support" element={<Navigate to="/" replace />} />
            <Route path="/support/inquiry" element={<InquiryDetails />} />
            <Route path="/support/chat" element={<ChatSupport />} />
            <Route path="/support/status" element={<TicketStatus />} />
            <Route path="/support/docs" element={<Documentation />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin" element={<RequireAdmin><AgentDashboard /></RequireAdmin>} />
            <Route path="/agent" element={<RequireAdmin><AgentDashboard /></RequireAdmin>} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </SupportProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertOctagon,
  ArrowLeft,
  ArrowUpCircle,
  CheckCheck,
  CheckCircle2,
  Clock,
  Eye,
  FileText,
  LoaderCircle,
  LogOut,
  MessageSquareText,
  RefreshCw,
  Save,
  Ticket as TicketIcon,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StatusBadge } from "@/components/support/StatusBadge";
import { clearAdminSession, getAdminSession } from "@/lib/adminSession";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface AdminAgent {
  id: number;
  username: string;
  fullName: string;
  email: string | null;
  role: string;
}

interface TicketSummary {
  id: string;
  learnerName: string;
  email: string;
  category: string;
  technicalSubcategory: string;
  status: "Open" | "Pending" | "In Progress" | "Resolved" | "Closed";
  assignedAgentId: number | null;
  assignedAgentName: string;
  assignedAgentUsername: string;
  assignedTeam: string;
  slaStatus: "Pending Review" | "On Track" | "Breached";
  evidenceCount: number;
  createdAt: string;
  updatedAt: string;
}

interface TicketDetail extends TicketSummary {
  inquiry: string;
  priority: string;
  closedAt: string | null;
}

interface ChatHistoryItem {
  id: number;
  role: string;
  senderLabel: string;
  text: string;
  createdAt: string;
}

interface AttachmentItem {
  id: number;
  name: string;
  mimeType: string | null;
  size: number;
  storageUrl: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

interface HistoryItem {
  id: number;
  eventType: string;
  actorType: string;
  actorLabel: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
}

interface SessionRequestItem {
  id: number;
  requestedDate: string;
  requestedTime: string;
  status: string;
  createdBy: string;
  notes: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

interface TicketDetailResponse {
  ticket: TicketDetail;
  chatHistory: ChatHistoryItem[];
  attachments: AttachmentItem[];
  history: HistoryItem[];
  sessionRequests: SessionRequestItem[];
}

interface ListResponse {
  message?: string;
  tickets?: TicketSummary[];
  agents?: AdminAgent[];
}

interface DetailResponse extends TicketDetailResponse {
  message?: string;
}

const statuses: TicketSummary["status"][] = ["Open", "Pending", "In Progress", "Resolved", "Closed"];
const slaStatuses: TicketSummary["slaStatus"][] = ["Pending Review", "On Track", "Breached"];

const AgentDashboard = () => {
  const navigate = useNavigate();
  const session = getAdminSession();
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [agents, setAgents] = useState<AdminAgent[]>([]);
  const [activeTicketId, setActiveTicketId] = useState("");
  const [activeDetail, setActiveDetail] = useState<TicketDetailResponse | null>(null);
  const [draftStatus, setDraftStatus] = useState<TicketSummary["status"]>("Open");
  const [draftAgentId, setDraftAgentId] = useState("unassigned");
  const [draftSlaStatus, setDraftSlaStatus] = useState<TicketSummary["slaStatus"]>("Pending Review");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isOpening, setIsOpening] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadDashboard();
  }, []);

  const kpis = [
    {
      label: "Open Tickets",
      value: tickets.filter((ticket) => ticket.status === "Open").length,
      icon: TicketIcon,
      color: "text-info bg-info/10",
    },
    {
      label: "Pending Tickets",
      value: tickets.filter((ticket) => ticket.status === "Pending").length,
      icon: Clock,
      color: "text-warning bg-warning/10",
    },
    {
      label: "Closed Tickets",
      value: tickets.filter((ticket) => ticket.status === "Closed").length,
      icon: CheckCircle2,
      color: "text-success bg-success/10",
    },
    {
      label: "SLA Breaches",
      value: tickets.filter((ticket) => ticket.slaStatus === "Breached").length,
      icon: AlertOctagon,
      color: "text-destructive bg-destructive/10",
    },
  ];

  async function loadDashboard() {
    setIsLoading(true);
    setError("");

    try {
      const [ticketsResponse, agentsResponse] = await Promise.all([
        fetch("/api/admin/tickets"),
        fetch("/api/admin/agents"),
      ]);

      const ticketsPayload = (await ticketsResponse.json().catch(() => null)) as ListResponse | null;
      const agentsPayload = (await agentsResponse.json().catch(() => null)) as ListResponse | null;

      if (!ticketsResponse.ok) {
        throw new Error(ticketsPayload?.message || "We could not load tickets right now.");
      }

      if (!agentsResponse.ok) {
        throw new Error(agentsPayload?.message || "We could not load agents right now.");
      }

      setTickets(ticketsPayload?.tickets || []);
      setAgents(agentsPayload?.agents || []);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "We could not load the dashboard right now.");
    } finally {
      setIsLoading(false);
    }
  }

  async function openTicket(ticketId: string) {
    setActiveTicketId(ticketId);
    setActiveDetail(null);
    setNotes("");
    setIsOpening(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(ticketId)}`);
      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || "We could not load this ticket right now.");
        return;
      }

      setActiveDetail(payload);
      syncDrafts(payload);
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsOpening(false);
    }
  }

  function syncDrafts(detail: TicketDetailResponse) {
    setDraftStatus(detail.ticket.status);
    setDraftAgentId(detail.ticket.assignedAgentId ? String(detail.ticket.assignedAgentId) : "unassigned");
    setDraftSlaStatus(detail.ticket.slaStatus);
    setNotes("");
  }

  function closePanel() {
    setActiveTicketId("");
    setActiveDetail(null);
    setNotes("");
  }

  async function saveTicket(overrides?: {
    status?: TicketSummary["status"];
    slaStatus?: TicketSummary["slaStatus"];
    note?: string;
    successMessage?: string;
  }) {
    if (!activeDetail) {
      return;
    }

    setIsSaving(true);

    try {
      const response = await fetch(`/api/admin/tickets/${encodeURIComponent(activeDetail.ticket.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: overrides?.status ?? draftStatus,
          assignedAgentId: draftAgentId === "unassigned" ? null : Number(draftAgentId),
          slaStatus: overrides?.slaStatus ?? draftSlaStatus,
          note: overrides?.note ?? notes,
          actorUsername: session?.username || "admin",
        }),
      });

      const payload = (await response.json().catch(() => null)) as DetailResponse | null;

      if (!response.ok || !payload?.ticket) {
        toast.error(payload?.message || "We could not update the ticket right now.");
        return;
      }

      setActiveDetail(payload);
      syncDrafts(payload);
      setTickets((currentTickets) => currentTickets.map((ticket) => (
        ticket.id === payload.ticket.id ? payload.ticket : ticket
      )));
      toast.success(overrides?.successMessage || "Changes saved");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SupportLayout>
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
          <div>
            <h1 className="text-3xl font-bold">Admin Dashboard</h1>
            <p className="text-muted-foreground text-sm">
              Manage learner tickets, assignments, chat history and SLA actions.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Signed in as {session?.fullName || session?.username || "Support Admin"} ({session?.role || "admin"})
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/"><ArrowLeft className="h-4 w-4 mr-2" /> Back</Link>
            </Button>
            <Button variant="outline" size="sm" onClick={() => void loadDashboard()} disabled={isLoading}>
              <RefreshCw className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")} /> Refresh
            </Button>
            <LogoutButton />
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {kpis.map((kpi) => (
            <div key={kpi.label} className="bg-card rounded-2xl border shadow-soft p-5">
              <div className={cn("h-9 w-9 rounded-lg flex items-center justify-center mb-3", kpi.color)}>
                <kpi.icon className="h-5 w-5" />
              </div>
              <div className="text-2xl font-bold">{kpi.value}</div>
              <div className="text-xs text-muted-foreground">{kpi.label}</div>
            </div>
          ))}
        </div>

        <div className="bg-card rounded-2xl border shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b flex items-center justify-between">
            <h2 className="font-semibold">Recent Tickets</h2>
            <span className="text-xs text-muted-foreground">{tickets.length} total</span>
          </div>

          {error ? (
            <div className="p-5 text-sm text-destructive bg-destructive/5 border-b border-destructive/10">
              {error}
            </div>
          ) : null}

          {isLoading ? (
            <div className="p-10 text-sm text-muted-foreground flex items-center justify-center gap-2">
              <LoaderCircle className="h-4 w-4 animate-spin" /> Loading dashboard...
            </div>
          ) : tickets.length === 0 ? (
            <div className="p-10 text-sm text-muted-foreground text-center">
              No tickets have been created yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/50 text-muted-foreground">
                  <tr className="text-left">
                    {["Ticket ID", "Learner", "Category", "Status", "Assigned Agent", "Created", "SLA", "Action"].map((heading) => (
                      <th key={heading} className="px-4 py-3 font-medium whitespace-nowrap">{heading}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {tickets.map((ticket) => (
                    <tr key={ticket.id} className="hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-3 font-mono font-medium whitespace-nowrap">{ticket.id}</td>
                      <td className="px-4 py-3 min-w-[240px]">
                        <div className="font-medium">{ticket.learnerName || "Learner"}</div>
                        <div className="text-xs text-muted-foreground">{ticket.email}</div>
                      </td>
                      <td className="px-4 py-3">{formatCategoryLabel(ticket.category, ticket.technicalSubcategory)}</td>
                      <td className="px-4 py-3"><StatusBadge status={ticket.status} /></td>
                      <td className="px-4 py-3">{ticket.assignedAgentName}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{formatDateShort(ticket.createdAt)}</td>
                      <td className="px-4 py-3">
                        <span className={cn("text-xs font-medium", slaStatusClassName(ticket.slaStatus))}>
                          {ticket.slaStatus}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <Button size="sm" variant="outline" onClick={() => void openTicket(ticket.id)}>
                          <Eye className="h-3.5 w-3.5 mr-1.5" /> View
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <Sheet open={!!activeTicketId} onOpenChange={(open) => !open && closePanel()}>
        <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
          {isOpening ? (
            <div className="h-full min-h-[300px] flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="h-4 w-4 animate-spin" /> Loading ticket...
            </div>
          ) : activeDetail ? (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  Ticket <span className="font-mono">{activeDetail.ticket.id}</span>
                </SheetTitle>
                <SheetDescription>
                  {activeDetail.ticket.learnerName || activeDetail.ticket.email} - {formatCategoryLabel(activeDetail.ticket.category, activeDetail.ticket.technicalSubcategory)}
                </SheetDescription>
              </SheetHeader>

              <div className="space-y-5 py-5">
                <div className="grid gap-3 md:grid-cols-3">
                  <div>
                    <Label className="mb-1.5 block">Status</Label>
                    <Select value={draftStatus} onValueChange={(value) => setDraftStatus(value as TicketSummary["status"])}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {statuses.map((status) => (
                          <SelectItem key={status} value={status}>{status}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="mb-1.5 block">Assign Agent</Label>
                    <Select value={draftAgentId} onValueChange={setDraftAgentId}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="unassigned">Unassigned</SelectItem>
                        {agents.map((agent) => (
                          <SelectItem key={agent.id} value={String(agent.id)}>
                            {agent.fullName}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="mb-1.5 block">SLA</Label>
                    <Select value={draftSlaStatus} onValueChange={(value) => setDraftSlaStatus(value as TicketSummary["slaStatus"])}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {slaStatuses.map((status) => (
                          <SelectItem key={status} value={status}>{status}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid gap-4 text-sm sm:grid-cols-2">
                  <InfoCard label="Learner Email" value={activeDetail.ticket.email} />
                  <InfoCard label="Assigned Team" value={activeDetail.ticket.assignedTeam} />
                  <InfoCard label="Category" value={formatCategoryLabel(activeDetail.ticket.category, activeDetail.ticket.technicalSubcategory)} />
                  <InfoCard label="Created" value={formatDateTime(activeDetail.ticket.createdAt)} />
                  <InfoCard label="Updated" value={formatDateTime(activeDetail.ticket.updatedAt)} />
                  <InfoCard label="Priority" value={activeDetail.ticket.priority} />
                  <InfoCard label="Evidence Count" value={String(activeDetail.ticket.evidenceCount)} />
                </div>

                <section>
                  <Label className="mb-1.5 block">Inquiry details</Label>
                  <div className="rounded-xl border bg-secondary/40 p-3 text-sm leading-6">
                    {activeDetail.ticket.inquiry}
                  </div>
                </section>

                <section>
                  <Label className="mb-1.5 block">Support session requests</Label>
                  <div className="rounded-xl border p-3 space-y-3">
                    {activeDetail.sessionRequests.length === 0 ? (
                      <div className="text-sm text-muted-foreground">No session requests for this ticket yet.</div>
                    ) : (
                      activeDetail.sessionRequests.map((request) => (
                        <div key={request.id} className="rounded-lg bg-secondary/40 p-3 text-sm">
                          <div className="font-medium">
                            {request.requestedDate} at {request.requestedTime}
                          </div>
                          <div className="text-muted-foreground text-xs mt-1">
                            Status: {request.status} - Requested by: {request.createdBy} - {formatDateTime(request.createdAt)}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                <section>
                  <Label className="mb-1.5 block">Chat history</Label>
                  <div className="space-y-2 max-h-64 overflow-y-auto rounded-xl border p-3">
                    {activeDetail.chatHistory.length === 0 ? (
                      <div className="text-sm text-muted-foreground">No chat messages stored for this ticket yet.</div>
                    ) : (
                      activeDetail.chatHistory.map((message) => (
                        <div key={message.id} className="rounded-lg bg-secondary/40 p-3">
                          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                            <span className="font-medium text-foreground">{message.senderLabel}</span>
                            <span>{formatDateTime(message.createdAt)}</span>
                          </div>
                          <div className="mt-1 text-sm leading-6">{message.text}</div>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                <section>
                  <Label className="mb-1.5 block">Uploaded evidence</Label>
                  <div className="rounded-xl border p-3 space-y-3">
                    {activeDetail.attachments.length === 0 ? (
                      <div className="text-sm text-muted-foreground">No files attached to this ticket.</div>
                    ) : (
                      activeDetail.attachments.map((file) => (
                        <div key={file.id} className="flex items-start justify-between gap-3 rounded-lg bg-secondary/40 p-3">
                          <div className="min-w-0">
                            <div className="font-medium flex items-center gap-2">
                              <FileText className="h-4 w-4 shrink-0" />
                              <span className="truncate">{file.name}</span>
                            </div>
                            <div className="text-xs text-muted-foreground mt-1">
                              {(file.mimeType || "Unknown type")} - {formatBytes(file.size)} - {formatDateTime(file.createdAt)}
                            </div>
                            {!file.storageUrl && (
                              <div className="text-xs text-muted-foreground mt-1">
                                File storage URL is not set yet. Only metadata is stored currently.
                              </div>
                            )}
                          </div>
                          {file.storageUrl ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => window.open(file.storageUrl || "", "_blank", "noopener,noreferrer")}
                            >
                              Open
                            </Button>
                          ) : null}
                        </div>
                      ))
                    )}
                  </div>
                </section>

                <section>
                  <Label className="mb-1.5 block">Activity log</Label>
                  <div className="rounded-xl border p-3 space-y-3 max-h-64 overflow-y-auto">
                    {activeDetail.history.length === 0 ? (
                      <div className="text-sm text-muted-foreground">No activity has been recorded yet.</div>
                    ) : (
                      activeDetail.history.map((item) => (
                        <div key={item.id} className="rounded-lg bg-secondary/40 p-3">
                          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                            <span className="font-medium text-foreground">{humanizeEvent(item.eventType)}</span>
                            <span>{formatDateTime(item.createdAt)}</span>
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">
                            {item.actorLabel || item.actorType}
                          </div>
                          <pre className="mt-2 text-xs whitespace-pre-wrap break-words text-muted-foreground">
                            {JSON.stringify(item.payload, null, 2)}
                          </pre>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                <section>
                  <Label className="mb-1.5 block">Internal notes</Label>
                  <Textarea
                    rows={4}
                    placeholder="Add an internal note visible to support staff only..."
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                  />
                </section>
              </div>

              <SheetFooter className="flex-col gap-2">
                <Button
                  className="w-full gradient-primary border-0"
                  onClick={() => void saveTicket({ successMessage: "Changes saved" })}
                  disabled={isSaving}
                >
                  {isSaving ? <LoaderCircle className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                  Save Changes
                </Button>
                <div className="grid gap-2 sm:grid-cols-3">
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => void saveTicket({
                      status: "In Progress",
                      slaStatus: "Breached",
                      note: notes || "Escalated from admin dashboard.",
                      successMessage: "Ticket escalated",
                    })}
                    disabled={isSaving}
                  >
                    <ArrowUpCircle className="h-4 w-4 mr-2" /> Escalate
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => void saveTicket({
                      status: "Resolved",
                      successMessage: "Marked as resolved",
                    })}
                    disabled={isSaving}
                  >
                    <CheckCheck className="h-4 w-4 mr-2" /> Resolve
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => void saveTicket({
                      status: "Closed",
                      successMessage: "Ticket closed",
                    })}
                    disabled={isSaving}
                  >
                    <X className="h-4 w-4 mr-2" /> Close
                  </Button>
                </div>
              </SheetFooter>
            </>
          ) : (
            <div className="h-full min-h-[300px] flex items-center justify-center text-sm text-muted-foreground">
              Select a ticket to view its details.
            </div>
          )}
        </SheetContent>
      </Sheet>
    </SupportLayout>
  );
};

const InfoCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-xl border p-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className="font-medium mt-1 break-words">{value}</div>
  </div>
);

const LogoutButton = () => {
  const navigate = useNavigate();

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        clearAdminSession();
        navigate("/admin/login");
      }}
    >
      <LogOut className="h-4 w-4 mr-2" /> Logout
    </Button>
  );
};

function formatDateShort(value: string) {
  return new Date(value).toLocaleDateString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(value: number) {
  if (!value) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatCategoryLabel(category: string, technicalSubcategory: string) {
  if (category === "Technical" && technicalSubcategory) {
    return `${category} - ${technicalSubcategory}`;
  }

  return category;
}

function humanizeEvent(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function slaStatusClassName(value: TicketSummary["slaStatus"]) {
  if (value === "Breached") return "text-destructive";
  if (value === "On Track") return "text-success";
  return "text-warning";
}

export default AgentDashboard;

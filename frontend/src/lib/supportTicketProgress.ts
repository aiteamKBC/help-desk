export async function setTicketBookingProgress(ticketId: string, active: boolean) {
  if (!ticketId) {
    return;
  }

  await fetch(`/api/tickets/${encodeURIComponent(ticketId)}/booking-progress`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ active }),
  }).catch(() => null);
}

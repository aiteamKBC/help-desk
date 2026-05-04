from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("migration-status", views.migration_status, name="migration-status"),
    path("verify-email", views.verify_email, name="verify-email"),
    path("admin/login", views.admin_login, name="admin-login"),
    path("admin/agents", views.admin_agents, name="admin-agents"),
    path("admin/tickets", views.admin_tickets, name="admin-tickets"),
    path("admin/tickets/<str:public_id>", views.admin_ticket_detail, name="admin-ticket-detail"),
    path("tickets", views.tickets_create, name="tickets-create"),
    path("tickets/<str:public_id>", views.tickets_update, name="tickets-update"),
    path("tickets/<str:public_id>/chat-history", views.ticket_chat_history, name="ticket-chat-history"),
    path("tickets/<str:public_id>/chatbot-message", views.ticket_chatbot_message, name="ticket-chatbot-message"),
    path("tickets/<str:public_id>/session-requests", views.ticket_session_request, name="ticket-session-request"),
]

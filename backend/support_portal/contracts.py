LEGACY_ENDPOINTS = [
    {"method": "POST", "path": "/api/verify-email"},
    {"method": "POST", "path": "/api/admin/login"},
    {"method": "GET", "path": "/api/admin/agents"},
    {"method": "GET", "path": "/api/admin/tickets"},
    {"method": "GET", "path": "/api/admin/tickets/:publicId"},
    {"method": "PATCH", "path": "/api/admin/tickets/:publicId"},
    {"method": "POST", "path": "/api/tickets"},
    {"method": "PATCH", "path": "/api/tickets/:publicId"},
    {"method": "POST", "path": "/api/tickets/:publicId/chat-history"},
    {"method": "POST", "path": "/api/tickets/:publicId/chatbot-message"},
    {"method": "POST", "path": "/api/tickets/:publicId/session-requests"},
]

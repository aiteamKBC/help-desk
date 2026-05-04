import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";
import { databaseUrl, ensurePool, withTransaction } from "./lib/db.mjs";

const app = express();
const port = Number(process.env.PORT || 3001);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distPath = path.resolve(__dirname, "../frontend/dist");
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const sharedSupportPassword = process.env.SUPPORT_PORTAL_PASSWORD?.trim() || "admin123";
const allowedStatuses = new Set(["Open", "Pending", "In Progress", "Resolved", "Closed"]);
const allowedCategories = new Set(["Learning", "Technical", "Others"]);
const allowedTechnicalSubcategories = new Set(["Aptem", "LMS", "Teams"]);
const allowedSlaStatuses = new Set(["Pending Review", "On Track", "Breached"]);

app.use(express.json({ limit: "10mb" }));

app.get("/api/health", (_req, res) => {
  res.json({
    ok: true,
    databaseConfigured: Boolean(databaseUrl),
  });
});

app.post("/api/verify-email", async (req, res) => {
  const email = normalizeEmail(req.body?.email);

  if (!isValidEmail(email)) {
    return res.status(400).json({
      exists: false,
      message: "Please enter a valid email address.",
    });
  }

  try {
    const result = await ensurePool().query(
      `
        SELECT id, full_name, email
        FROM learners
        WHERE email = $1
        LIMIT 1
      `,
      [email],
    );

    const learner = result.rows[0];

    if (!learner) {
      return res.status(404).json({
        exists: false,
        message: "This email is not registered in our records.",
      });
    }

    return res.json({
      exists: true,
      learner: {
        id: learner.id,
        fullName: learner.full_name,
        email: learner.email,
      },
      message: "Email verified.",
    });
  } catch (error) {
    console.error("Email verification failed:", error);
    return res.status(500).json({
      exists: false,
      message: "We could not verify this email right now. Please try again.",
    });
  }
});

app.post("/api/admin/login", async (req, res) => {
  const username = sanitizeText(req.body?.username).toLowerCase();
  const password = typeof req.body?.password === "string" ? req.body.password : "";

  if (!username || !password) {
    return res.status(400).json({ message: "Username and password are required." });
  }

  try {
    const result = await ensurePool().query(
      `
        SELECT id, username, full_name, email, role
        FROM agents
        WHERE LOWER(username) = $1
          AND is_active = TRUE
        LIMIT 1
      `,
      [username],
    );

    const agent = result.rows[0];
    if (!agent || password !== sharedSupportPassword) {
      return res.status(401).json({ message: "Invalid username or password." });
    }

    return res.json({
      admin: serializeAgent(agent),
      message: "Login successful.",
    });
  } catch (error) {
    console.error("Admin login failed:", error);
    return res.status(500).json({ message: "We could not sign you in right now." });
  }
});

app.get("/api/admin/agents", async (_req, res) => {
  try {
    const result = await ensurePool().query(
      `
        SELECT id, username, full_name, email, role
        FROM agents
        WHERE is_active = TRUE
        ORDER BY role DESC, full_name ASC NULLS LAST, username ASC
      `,
    );

    return res.json({
      agents: result.rows.map(serializeAgent),
    });
  } catch (error) {
    console.error("Agents fetch failed:", error);
    return res.status(500).json({ message: "We could not load the agent list right now." });
  }
});

app.get("/api/admin/tickets", async (_req, res) => {
  try {
    const result = await ensurePool().query(
      `
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.status,
          t.assigned_team,
          t.sla_status,
          t.evidence_count,
          t.created_at,
          t.updated_at,
          l.full_name AS learner_name,
          l.email AS learner_email,
          a.id AS assigned_agent_id,
          a.username AS assigned_agent_username,
          a.full_name AS assigned_agent_name
        FROM tickets t
        JOIN learners l
          ON l.id = t.learner_id
        LEFT JOIN agents a
          ON a.id = t.assigned_agent_id
        ORDER BY t.created_at DESC, t.id DESC
      `,
    );

    return res.json({
      tickets: result.rows.map(serializeTicketSummary),
    });
  } catch (error) {
    console.error("Admin tickets fetch failed:", error);
    return res.status(500).json({ message: "We could not load tickets right now." });
  }
});

app.get("/api/admin/tickets/:publicId", async (req, res) => {
  const publicId = sanitizeText(req.params.publicId);

  if (!publicId) {
    return res.status(400).json({ message: "Ticket id is required." });
  }

  try {
    const detail = await fetchAdminTicketDetail(ensurePool(), publicId);
    if (!detail) {
      return res.status(404).json({ message: "Ticket not found." });
    }

    return res.json(detail);
  } catch (error) {
    console.error("Admin ticket detail fetch failed:", error);
    return res.status(500).json({ message: "We could not load the ticket details right now." });
  }
});

app.patch("/api/admin/tickets/:publicId", async (req, res) => {
  const publicId = sanitizeText(req.params.publicId);
  const requestedStatus = req.body?.status === undefined ? undefined : sanitizeText(req.body.status);
  const requestedSlaStatus = req.body?.slaStatus === undefined ? undefined : sanitizeText(req.body.slaStatus);
  const requestedAssignedTeam = req.body?.assignedTeam === undefined ? undefined : sanitizeText(req.body.assignedTeam);
  const actorUsername = sanitizeText(req.body?.actorUsername).toLowerCase();
  const note = typeof req.body?.note === "string" ? req.body.note.trim() : "";
  const assignedAgentIdValue = req.body?.assignedAgentId;
  const hasAssignedAgentInput = Object.prototype.hasOwnProperty.call(req.body ?? {}, "assignedAgentId");

  if (!publicId) {
    return res.status(400).json({ message: "Ticket id is required." });
  }

  if (requestedStatus !== undefined && !allowedStatuses.has(requestedStatus)) {
    return res.status(400).json({ message: "Invalid ticket status." });
  }

  if (requestedSlaStatus !== undefined && !allowedSlaStatuses.has(requestedSlaStatus)) {
    return res.status(400).json({ message: "Invalid SLA status." });
  }

  const parsedAssignedAgentId = hasAssignedAgentInput ? parseAssignedAgentId(assignedAgentIdValue) : undefined;
  if (Number.isNaN(parsedAssignedAgentId)) {
    return res.status(400).json({ message: "Invalid assigned agent." });
  }

  try {
    const detail = await withTransaction(async (client) => {
      const ticketResult = await client.query(
        `
          SELECT
            t.id,
            t.public_id,
            t.status,
            t.assigned_agent_id,
            t.assigned_team,
            t.sla_status,
            t.closed_at,
            t.conversation_id,
            a.username AS assigned_agent_username,
            a.full_name AS assigned_agent_name
          FROM tickets t
          LEFT JOIN agents a
            ON a.id = t.assigned_agent_id
          WHERE t.public_id = $1
          LIMIT 1
        `,
        [publicId],
      );

      const ticket = ticketResult.rows[0];
      if (!ticket) {
        throw httpError(404, "Ticket not found.");
      }

      const actor = actorUsername
        ? await fetchActorByUsername(client, actorUsername)
        : null;

      let assignedAgent = null;
      if (hasAssignedAgentInput && parsedAssignedAgentId !== null) {
        const agentResult = await client.query(
          `
            SELECT id, username, full_name, email, role
            FROM agents
            WHERE id = $1
              AND is_active = TRUE
            LIMIT 1
          `,
          [parsedAssignedAgentId],
        );

        assignedAgent = agentResult.rows[0];
        if (!assignedAgent) {
          throw httpError(400, "The selected agent does not exist.");
        }
      } else if (!hasAssignedAgentInput && ticket.assigned_agent_id) {
        assignedAgent = {
          id: ticket.assigned_agent_id,
          username: ticket.assigned_agent_username,
          full_name: ticket.assigned_agent_name,
          email: null,
          role: "agent",
        };
      }

      const nextStatus = requestedStatus ?? ticket.status;
      const nextSlaStatus = requestedSlaStatus ?? ticket.sla_status;
      const nextAssignedAgentId = hasAssignedAgentInput
        ? parsedAssignedAgentId
        : ticket.assigned_agent_id;
      const nextAssignedTeam = requestedAssignedTeam !== undefined
        ? requestedAssignedTeam || deriveAssignedTeam(assignedAgent)
        : hasAssignedAgentInput
          ? deriveAssignedTeam(assignedAgent)
          : ticket.assigned_team;

      await client.query(
        `
          UPDATE tickets
          SET
            status = $1,
            assigned_agent_id = $2,
            assigned_team = $3,
            sla_status = $4,
            updated_at = NOW(),
            closed_at = CASE
              WHEN $1 = 'Closed' THEN NOW()
              WHEN status = 'Closed' AND $1 <> 'Closed' THEN NULL
              ELSE closed_at
            END
          WHERE id = $5
        `,
        [nextStatus, nextAssignedAgentId, nextAssignedTeam, nextSlaStatus, ticket.id],
      );

      if (ticket.conversation_id) {
        await client.query(
          `
            UPDATE conversations
            SET
              status = $1,
              last_message_at = NOW(),
              metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb
            WHERE id = $3
          `,
          [
            mapConversationStatus(nextStatus),
            JSON.stringify({
              ticket_status: nextStatus,
              assigned_agent_id: nextAssignedAgentId,
              assigned_team: nextAssignedTeam,
            }),
            ticket.conversation_id,
          ],
        );
      }

      if (ticket.status !== nextStatus) {
        await insertHistoryEvent(client, {
          ticketId: ticket.id,
          eventType: "status_changed",
          actor,
          payload: { from: ticket.status, to: nextStatus },
        });
      }

      if ((ticket.assigned_agent_id ?? null) !== (nextAssignedAgentId ?? null)) {
        await insertHistoryEvent(client, {
          ticketId: ticket.id,
          eventType: "assignment_changed",
          actor,
          payload: {
            fromAgentId: ticket.assigned_agent_id,
            toAgentId: nextAssignedAgentId,
            toAgentName: assignedAgent?.full_name || null,
          },
        });
      }

      if (ticket.sla_status !== nextSlaStatus) {
        await insertHistoryEvent(client, {
          ticketId: ticket.id,
          eventType: "sla_changed",
          actor,
          payload: { from: ticket.sla_status, to: nextSlaStatus },
        });
      }

      if (note) {
        await insertHistoryEvent(client, {
          ticketId: ticket.id,
          eventType: "internal_note",
          actor,
          payload: { note },
        });
      }

      return fetchAdminTicketDetail(client, publicId);
    });

    return res.json(detail);
  } catch (error) {
    console.error("Admin ticket update failed:", error);
    return res.status(error.statusCode || 500).json({
      message: error.statusCode ? error.message : "We could not update the ticket right now.",
    });
  }
});

app.post("/api/tickets", async (req, res) => {
  const email = normalizeEmail(req.body?.email);
  const category = typeof req.body?.category === "string" ? req.body.category.trim() : "";
  const technicalSubcategory = normalizeTechnicalSubcategory(req.body?.technicalSubcategory);
  const inquiry = typeof req.body?.inquiry === "string" ? req.body.inquiry.trim() : "";
  const evidence = Array.isArray(req.body?.evidence) ? req.body.evidence : [];

  if (!isValidEmail(email)) {
    return res.status(400).json({ message: "Please enter a valid email address." });
  }

  if (!allowedCategories.has(category)) {
    return res.status(400).json({ message: "Please choose a valid inquiry category." });
  }

  if (category === "Technical" && !technicalSubcategory) {
    return res.status(400).json({ message: "Please choose a technical sub category." });
  }

  if (category !== "Technical" && technicalSubcategory) {
    return res.status(400).json({ message: "Technical sub category can only be used with Technical inquiries." });
  }

  if (!inquiry) {
    return res.status(400).json({ message: "Inquiry details are required." });
  }

  try {
    const ticket = await withTransaction(async (client) => {
      const learnerResult = await client.query(
        `
          SELECT id, full_name, email, phone
          FROM learners
          WHERE email = $1
          LIMIT 1
        `,
        [email],
      );

      const learner = learnerResult.rows[0];
      if (!learner) {
        throw httpError(404, "This email is not registered in our records.");
      }

      const draftPublicId = `TMP-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const ticketInsert = await client.query(
        `
          INSERT INTO tickets (
            public_id,
            learner_id,
            category,
            technical_subcategory,
            inquiry,
            evidence_count,
            metadata
          )
          VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
          RETURNING id, status, assigned_team, sla_status, created_at
        `,
        [
          draftPublicId,
          learner.id,
          category,
          technicalSubcategory || null,
          inquiry,
          evidence.length,
          JSON.stringify({ source: "support_portal", technical_subcategory: technicalSubcategory || null }),
        ],
      );

      const ticketRow = ticketInsert.rows[0];
      const publicId = buildPublicTicketId(ticketRow.id);

      const conversationInsert = await client.query(
        `
          INSERT INTO conversations (
            channel,
            customer_id,
            customer_name,
            customer_email,
            customer_phone,
            status,
            intent,
            language,
            created_at,
            last_message_at,
            metadata
          )
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), $9::jsonb)
          RETURNING id
        `,
        [
          "support",
          publicId,
          learner.full_name,
          learner.email,
          learner.phone,
          "open",
          category,
          "en",
          JSON.stringify({ ticket_public_id: publicId, learner_id: learner.id, technical_subcategory: technicalSubcategory || null }),
        ],
      );

      const conversationId = conversationInsert.rows[0].id;

      await client.query(
        `
          UPDATE tickets
          SET public_id = $1, conversation_id = $2, updated_at = NOW()
          WHERE id = $3
        `,
        [publicId, conversationId, ticketRow.id],
      );

      if (evidence.length > 0) {
        const values = [];
        const placeholders = evidence.map((file, index) => {
          const offset = index * 6;
          values.push(
            ticketRow.id,
            sanitizeText(file?.name),
            sanitizeText(file?.mimeType),
            toNullableBigInt(file?.size),
            null,
            JSON.stringify(file ?? {}),
          );
          return `($${offset + 1}, $${offset + 2}, $${offset + 3}, $${offset + 4}, $${offset + 5}, $${offset + 6}::jsonb)`;
        });

        await client.query(
          `
            INSERT INTO ticket_attachments (
              ticket_id,
              file_name,
              mime_type,
              file_size,
              storage_url,
              metadata
            )
            VALUES ${placeholders.join(", ")}
          `,
          values,
        );
      }

      await insertHistoryEvent(client, {
        ticketId: ticketRow.id,
        eventType: "ticket_created",
        actor: {
          role: "learner",
          label: learner.email,
        },
        payload: { category, technical_subcategory: technicalSubcategory || null, evidence_count: evidence.length },
      });

      return {
        id: publicId,
        email: learner.email,
        category,
        technicalSubcategory,
        inquiry,
        status: ticketRow.status,
        assignedTeam: ticketRow.assigned_team,
        slaStatus: ticketRow.sla_status,
        createdAt: ticketRow.created_at,
      };
    });

    return res.status(201).json({ ticket });
  } catch (error) {
    console.error("Ticket creation failed:", error);
    return res.status(error.statusCode || 500).json({
      message: error.statusCode ? error.message : "We could not create the ticket right now.",
    });
  }
});

app.patch("/api/tickets/:publicId", async (req, res) => {
  const publicId = sanitizeText(req.params.publicId);
  const category = typeof req.body?.category === "string" ? req.body.category.trim() : "";
  const technicalSubcategory = normalizeTechnicalSubcategory(req.body?.technicalSubcategory);
  const inquiry = typeof req.body?.inquiry === "string" ? req.body.inquiry.trim() : "";
  const evidence = Array.isArray(req.body?.evidence) ? req.body.evidence : [];

  if (!publicId) {
    return res.status(400).json({ message: "Ticket id is required." });
  }

  if (!allowedCategories.has(category)) {
    return res.status(400).json({ message: "Please choose a valid inquiry category." });
  }

  if (category === "Technical" && !technicalSubcategory) {
    return res.status(400).json({ message: "Please choose a technical sub category." });
  }

  if (category !== "Technical" && technicalSubcategory) {
    return res.status(400).json({ message: "Technical sub category can only be used with Technical inquiries." });
  }

  if (!inquiry) {
    return res.status(400).json({ message: "Inquiry details are required." });
  }

  try {
    const ticket = await withTransaction(async (client) => {
      const ticketResult = await client.query(
        `
          SELECT
            t.id,
            t.public_id,
            t.status,
            t.assigned_team,
            t.sla_status,
            t.created_at,
            t.conversation_id,
            t.technical_subcategory,
            l.email
          FROM tickets t
          JOIN learners l
            ON l.id = t.learner_id
          WHERE t.public_id = $1
          LIMIT 1
        `,
        [publicId],
      );

      const existingTicket = ticketResult.rows[0];
      if (!existingTicket) {
        throw httpError(404, "Ticket not found.");
      }

      await client.query(
        `
          UPDATE tickets
          SET
            category = $1,
            technical_subcategory = $2,
            inquiry = $3,
            evidence_count = $4,
            updated_at = NOW()
          WHERE id = $5
        `,
        [category, technicalSubcategory || null, inquiry, evidence.length, existingTicket.id],
      );

      if (existingTicket.conversation_id) {
        await client.query(
          `
            UPDATE conversations
            SET
              intent = $1,
              metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb,
              last_message_at = NOW()
            WHERE id = $3
          `,
          [
            category,
            JSON.stringify({
              ticket_category: category,
              technical_subcategory: technicalSubcategory || null,
              latest_inquiry: inquiry,
              evidence_count: evidence.length,
            }),
            existingTicket.conversation_id,
          ],
        );
      }

      await client.query("DELETE FROM ticket_attachments WHERE ticket_id = $1", [existingTicket.id]);

      if (evidence.length > 0) {
        const values = [];
        const placeholders = evidence.map((file, index) => {
          const offset = index * 6;
          values.push(
            existingTicket.id,
            sanitizeText(file?.name),
            sanitizeText(file?.mimeType),
            toNullableBigInt(file?.size),
            null,
            JSON.stringify(file ?? {}),
          );
          return `($${offset + 1}, $${offset + 2}, $${offset + 3}, $${offset + 4}, $${offset + 5}, $${offset + 6}::jsonb)`;
        });

        await client.query(
          `
            INSERT INTO ticket_attachments (
              ticket_id,
              file_name,
              mime_type,
              file_size,
              storage_url,
              metadata
            )
            VALUES ${placeholders.join(", ")}
          `,
          values,
        );
      }

      await insertHistoryEvent(client, {
        ticketId: existingTicket.id,
        eventType: "ticket_updated",
        actor: {
          role: "learner",
          label: existingTicket.email,
        },
        payload: {
          category,
          technical_subcategory: technicalSubcategory || null,
          evidence_count: evidence.length,
        },
      });

      return {
        id: existingTicket.public_id,
        email: existingTicket.email,
        category,
        technicalSubcategory,
        inquiry,
        status: existingTicket.status,
        assignedTeam: existingTicket.assigned_team,
        slaStatus: existingTicket.sla_status,
        createdAt: existingTicket.created_at,
      };
    });

    return res.json({ ticket });
  } catch (error) {
    console.error("Ticket update failed:", error);
    return res.status(error.statusCode || 500).json({
      message: error.statusCode ? error.message : "We could not update the ticket right now.",
    });
  }
});

app.post("/api/tickets/:publicId/chat-history", async (req, res) => {
  const publicId = sanitizeText(req.params.publicId);
  const status = typeof req.body?.status === "string" ? req.body.status.trim() : "Open";
  const messages = Array.isArray(req.body?.messages) ? req.body.messages : [];

  if (!publicId) {
    return res.status(400).json({ message: "Ticket id is required." });
  }

  if (!allowedStatuses.has(status)) {
    return res.status(400).json({ message: "Invalid ticket status." });
  }

  try {
    await withTransaction(async (client) => {
      const ticketResult = await client.query(
        `
          SELECT id, conversation_id
          FROM tickets
          WHERE public_id = $1
          LIMIT 1
        `,
        [publicId],
      );

      const ticket = ticketResult.rows[0];
      if (!ticket) {
        throw httpError(404, "Ticket not found.");
      }

      if (!ticket.conversation_id) {
        throw httpError(400, "This ticket is not linked to a conversation.");
      }

      await client.query("DELETE FROM messages WHERE conversation_id = $1", [ticket.conversation_id]);

      const filteredMessages = messages
        .map((message) => ({
          role: mapSenderToRole(message?.sender),
          content: sanitizeText(message?.text),
          metadata: {
            original_sender: sanitizeText(message?.sender),
            client_timestamp: sanitizeText(message?.timestamp),
          },
        }))
        .filter((message) => message.content);

      if (filteredMessages.length > 0) {
        const values = [];
        const placeholders = filteredMessages.map((message, index) => {
          const offset = index * 5;
          values.push(
            ticket.conversation_id,
            message.role,
            message.content,
            "support",
            JSON.stringify(message.metadata),
          );
          return `($${offset + 1}, $${offset + 2}, $${offset + 3}, $${offset + 4}, $${offset + 5}::jsonb)`;
        });

        await client.query(
          `
            INSERT INTO messages (
              conversation_id,
              role,
              content,
              channel,
              metadata
            )
            VALUES ${placeholders.join(", ")}
          `,
          values,
        );
      }

      await client.query(
        `
          UPDATE conversations
          SET status = $1, last_message_at = NOW(), metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb
          WHERE id = $3
        `,
        [mapConversationStatus(status), JSON.stringify({ synced_messages: filteredMessages.length }), ticket.conversation_id],
      );

      await client.query(
        `
          UPDATE tickets
          SET status = $1, updated_at = NOW(), closed_at = CASE WHEN $1 = 'Closed' THEN NOW() ELSE closed_at END
          WHERE id = $2
        `,
        [status, ticket.id],
      );

      await insertHistoryEvent(client, {
        ticketId: ticket.id,
        eventType: "chat_history_synced",
        actor: {
          role: "system",
          label: "support_portal",
        },
        payload: { message_count: filteredMessages.length, status },
      });
    });

    return res.json({ ok: true });
  } catch (error) {
    console.error("Chat history sync failed:", error);
    return res.status(error.statusCode || 500).json({
      message: error.statusCode ? error.message : "We could not save the chat history right now.",
    });
  }
});

app.post("/api/tickets/:publicId/session-requests", async (req, res) => {
  const publicId = sanitizeText(req.params.publicId);
  const requestedDate = typeof req.body?.date === "string" ? req.body.date.trim() : "";
  const requestedTime = typeof req.body?.time === "string" ? req.body.time.trim() : "";

  if (!publicId || !requestedDate || !requestedTime) {
    return res.status(400).json({ message: "Ticket id, date and time are required." });
  }

  try {
    await withTransaction(async (client) => {
      const ticketResult = await client.query(
        `
          SELECT id
          FROM tickets
          WHERE public_id = $1
          LIMIT 1
        `,
        [publicId],
      );

      const ticket = ticketResult.rows[0];
      if (!ticket) {
        throw httpError(404, "Ticket not found.");
      }

      await client.query(
        `
          INSERT INTO support_session_requests (
            ticket_id,
            requested_date,
            requested_time,
            metadata
          )
          VALUES ($1, $2, $3, $4::jsonb)
        `,
        [ticket.id, requestedDate, requestedTime, JSON.stringify({ source: "support_portal" })],
      );

      await insertHistoryEvent(client, {
        ticketId: ticket.id,
        eventType: "support_session_requested",
        actor: {
          role: "learner",
          label: publicId,
        },
        payload: { requestedDate, requestedTime },
      });
    });

    return res.status(201).json({ ok: true });
  } catch (error) {
    console.error("Support session request failed:", error);
    return res.status(error.statusCode || 500).json({
      message: error.statusCode ? error.message : "We could not save the support session request.",
    });
  }
});

if (existsSync(distPath)) {
  app.use(express.static(distPath));

  app.use((req, res, next) => {
    if (req.method !== "GET" || req.path.startsWith("/api/")) {
      next();
      return;
    }

    res.sendFile(path.join(distPath, "index.html"));
  });
}

app.listen(port, () => {
  console.log(`Support API listening on http://127.0.0.1:${port}`);

  if (!databaseUrl) {
    console.warn("DATABASE_URL is missing. Add it to backend/.env.local before starting the server.");
  }
});

async function fetchAdminTicketDetail(db, publicId) {
  const ticketResult = await db.query(
    `
        SELECT
          t.id,
          t.public_id,
          t.category,
          t.technical_subcategory,
          t.inquiry,
        t.status,
        t.assigned_team,
        t.sla_status,
        t.priority,
        t.evidence_count,
        t.created_at,
        t.updated_at,
        t.closed_at,
        t.conversation_id,
        l.full_name AS learner_name,
        l.email AS learner_email,
        a.id AS assigned_agent_id,
        a.username AS assigned_agent_username,
        a.full_name AS assigned_agent_name
      FROM tickets t
      JOIN learners l
        ON l.id = t.learner_id
      LEFT JOIN agents a
        ON a.id = t.assigned_agent_id
      WHERE t.public_id = $1
      LIMIT 1
    `,
    [publicId],
  );

  const ticket = ticketResult.rows[0];
  if (!ticket) {
    return null;
  }

  const [messagesResult, attachmentsResult, historyResult, sessionRequestsResult] = await Promise.all([
    ticket.conversation_id
      ? db.query(
          `
            SELECT id, role, content, metadata, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC, id ASC
          `,
          [ticket.conversation_id],
        )
      : Promise.resolve({ rows: [] }),
    db.query(
      `
        SELECT id, file_name, mime_type, file_size, storage_url, metadata, created_at
        FROM ticket_attachments
        WHERE ticket_id = $1
        ORDER BY created_at ASC, id ASC
      `,
      [ticket.id],
    ),
    db.query(
      `
        SELECT id, event_type, actor_type, actor_label, payload, created_at
        FROM ticket_history
        WHERE ticket_id = $1
        ORDER BY created_at DESC, id DESC
      `,
      [ticket.id],
    ),
    db.query(
      `
        SELECT id, requested_date, requested_time, status, created_by, notes, metadata, created_at
        FROM support_session_requests
        WHERE ticket_id = $1
        ORDER BY created_at DESC, id DESC
      `,
      [ticket.id],
    ),
  ]);

  return {
    ticket: serializeTicketDetail(ticket),
    chatHistory: messagesResult.rows.map((row) => ({
      id: row.id,
      role: row.role,
      senderLabel: toSenderLabel(row.role, row.metadata),
      text: row.content,
      createdAt: row.created_at,
    })),
    attachments: attachmentsResult.rows.map((row) => ({
      id: Number(row.id),
      name: row.file_name,
      mimeType: row.mime_type,
      size: row.file_size ? Number(row.file_size) : 0,
      storageUrl: row.storage_url,
      metadata: row.metadata ?? {},
      createdAt: row.created_at,
    })),
    history: historyResult.rows.map((row) => ({
      id: Number(row.id),
      eventType: row.event_type,
      actorType: row.actor_type,
      actorLabel: row.actor_label,
      payload: row.payload ?? {},
      createdAt: row.created_at,
    })),
    sessionRequests: sessionRequestsResult.rows.map((row) => ({
      id: Number(row.id),
      requestedDate: row.requested_date,
      requestedTime: row.requested_time,
      status: row.status,
      createdBy: row.created_by,
      notes: row.notes,
      metadata: row.metadata ?? {},
      createdAt: row.created_at,
    })),
  };
}

async function fetchActorByUsername(client, username) {
  const result = await client.query(
    `
      SELECT id, username, full_name, role
      FROM agents
      WHERE LOWER(username) = $1
      LIMIT 1
    `,
    [username],
  );

  const actor = result.rows[0];
  if (!actor) {
    return null;
  }

  return {
    id: actor.id,
    role: actor.role,
    label: actor.full_name || actor.username,
  };
}

async function insertHistoryEvent(client, { ticketId, eventType, actor, payload }) {
  await client.query(
    `
      INSERT INTO ticket_history (
        ticket_id,
        event_type,
        actor_type,
        actor_id,
        actor_label,
        payload
      )
      VALUES ($1, $2, $3, $4, $5, $6::jsonb)
    `,
    [
      ticketId,
      eventType,
      actor?.role || "system",
      actor?.id || null,
      actor?.label || null,
      JSON.stringify(payload ?? {}),
    ],
  );
}

function serializeAgent(row) {
  return {
    id: Number(row.id),
    username: row.username,
    fullName: row.full_name || row.username,
    email: row.email || null,
    role: row.role,
  };
}

function serializeTicketSummary(row) {
  return {
    id: row.public_id,
    learnerName: row.learner_name || "",
    email: row.learner_email,
    category: row.category,
    technicalSubcategory: row.technical_subcategory || "",
    status: row.status,
    assignedAgentId: row.assigned_agent_id ? Number(row.assigned_agent_id) : null,
    assignedAgentName: row.assigned_agent_name || "Unassigned",
    assignedAgentUsername: row.assigned_agent_username || "",
    assignedTeam: row.assigned_team || "Unassigned",
    slaStatus: row.sla_status,
    evidenceCount: Number(row.evidence_count || 0),
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function serializeTicketDetail(row) {
  return {
    ...serializeTicketSummary(row),
    inquiry: row.inquiry,
    priority: row.priority,
    closedAt: row.closed_at,
  };
}

function normalizeEmail(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function isValidEmail(email) {
  return emailPattern.test(email);
}

function normalizeTechnicalSubcategory(value) {
  const normalizedValue = sanitizeText(value);

  if (!normalizedValue) {
    return "";
  }

  const match = [...allowedTechnicalSubcategories].find(
    (item) => item.toLowerCase() === normalizedValue.toLowerCase(),
  );

  return match || "";
}

function buildPublicTicketId(id) {
  return `KBC-${String(id).padStart(6, "0")}`;
}

function sanitizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function toNullableBigInt(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }

  return null;
}

function mapSenderToRole(sender) {
  if (sender === "user") return "user";
  if (sender === "agent") return "agent";
  return "assistant";
}

function toSenderLabel(role, metadata) {
  const originalSender = sanitizeText(metadata?.original_sender);

  if (role === "user") return "Learner";
  if (role === "agent") return "Agent";
  if (originalSender === "bot") return "Bot";
  return "Support";
}

function parseAssignedAgentId(value) {
  if (value === null || value === "" || value === "unassigned") {
    return null;
  }

  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function deriveAssignedTeam(agent) {
  return agent ? "Support Desk" : "Unassigned";
}

function mapConversationStatus(status) {
  switch (status) {
    case "In Progress":
      return "in_progress";
    default:
      return status.toLowerCase();
  }
}

function httpError(statusCode, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  return error;
}

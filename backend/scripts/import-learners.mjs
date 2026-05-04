import pg from "pg";
import { ensurePool, legacyDatabaseUrl } from "../lib/db.mjs";

const { Client } = pg;
const BATCH_SIZE = 500;

if (!legacyDatabaseUrl) {
  console.error("LEGACY_DATABASE_URL is missing.");
  process.exit(1);
}

const targetPool = ensurePool();
const sourceClient = new Client({
  connectionString: legacyDatabaseUrl,
  ssl: { rejectUnauthorized: false },
});

function chunkArray(items, size) {
  const chunks = [];

  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }

  return chunks;
}

async function importBatch(batch) {
  const values = [];
  const placeholders = batch.map((learner, index) => {
    const offset = index * 6;
    values.push(
      learner.externalLearnerId,
      learner.fullName,
      learner.email,
      learner.phone,
      "legacy_kbc_users_data",
      JSON.stringify({ legacy_id: learner.externalLearnerId }),
    );

    return `($${offset + 1}, $${offset + 2}, $${offset + 3}, $${offset + 4}, $${offset + 5}, $${offset + 6}::jsonb)`;
  });

  await targetPool.query(
    `
      INSERT INTO learners (
        external_learner_id,
        full_name,
        email,
        phone,
        source,
        metadata
      )
      VALUES ${placeholders.join(", ")}
      ON CONFLICT (email) DO UPDATE
      SET
        external_learner_id = COALESCE(EXCLUDED.external_learner_id, learners.external_learner_id),
        full_name = COALESCE(EXCLUDED.full_name, learners.full_name),
        phone = COALESCE(EXCLUDED.phone, learners.phone),
        source = EXCLUDED.source,
        metadata = learners.metadata || EXCLUDED.metadata,
        updated_at = NOW()
    `,
    values,
  );
}

try {
  await sourceClient.connect();
  const sourceRows = await sourceClient.query(`
    SELECT DISTINCT
      NULLIF(TRIM("ID"::text), '') AS external_learner_id,
      NULLIF(TRIM(COALESCE("FullName", CONCAT_WS(' ', "FirstName", "LastName"))), '') AS full_name,
      LOWER(TRIM("Email")) AS email,
      NULLIF(TRIM(COALESCE("Learner_Phone", "learner-phone")), '') AS phone
    FROM kbc_users_data
    WHERE "Email" IS NOT NULL
      AND TRIM("Email") <> ''
  `);

  const deduped = new Map();
  for (const row of sourceRows.rows) {
    if (!row.email) continue;
    deduped.set(row.email, {
      externalLearnerId: row.external_learner_id,
      fullName: row.full_name,
      email: row.email,
      phone: row.phone,
    });
  }

  const batches = chunkArray([...deduped.values()], BATCH_SIZE);
  for (const batch of batches) {
    await importBatch(batch);
  }

  console.log(`Imported ${deduped.size} learners into learners table.`);
} finally {
  await sourceClient.end();
  await targetPool.end();
}

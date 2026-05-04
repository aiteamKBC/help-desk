import dotenv from "dotenv";
import pg from "pg";

dotenv.config({ path: ".env.local" });
dotenv.config();

const { Pool } = pg;

export function sanitizeDatabaseUrl(value) {
  if (!value) {
    return "";
  }

  try {
    const url = new URL(value);
    url.searchParams.delete("channel_binding");
    return url.toString();
  } catch {
    return value;
  }
}

export const databaseUrl = sanitizeDatabaseUrl(process.env.DATABASE_URL?.trim() || "");
export const legacyDatabaseUrl = sanitizeDatabaseUrl(process.env.LEGACY_DATABASE_URL?.trim() || "");

export const pool = databaseUrl
  ? new Pool({
      connectionString: databaseUrl,
      ssl: process.env.DATABASE_URL?.includes("sslmode=require")
        ? { rejectUnauthorized: false }
        : undefined,
    })
  : null;

if (pool) {
  pool.on("error", (error) => {
    console.error("Unexpected PostgreSQL error:", error);
  });
}

export function ensurePool() {
  if (!pool) {
    throw new Error("DATABASE_URL is missing.");
  }

  return pool;
}

export async function withTransaction(work) {
  const activePool = ensurePool();
  const client = await activePool.connect();

  try {
    await client.query("BEGIN");
    const result = await work(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

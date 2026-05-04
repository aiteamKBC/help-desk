import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ensurePool } from "../lib/db.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const migrationPath = path.resolve(__dirname, "../migrations/001_support_schema.sql");

const sql = await readFile(migrationPath, "utf8");
const pool = ensurePool();

try {
  await pool.query(sql);
  console.log("Migration applied successfully.");
} finally {
  await pool.end();
}

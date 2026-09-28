// Adapted from images@4aa2569 tests/http.mjs. Never stream response bodies.
import fs from "node:fs";

function sanitize(value) {
  return String(value).slice(0, 8192)
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\b(?:https?|ftp|file):\/\/[^\s<>"']+/gi, "[url]")
    .replace(/\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/gi, "[credential]")
    .replace(/\b(?:password|passwd|token|api[_-]?key|authorization|secret|cookie)["']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, "[credential]")
    .replace(/\b(?:sk-|ghp_|github_pat_|hf_)[A-Za-z0-9_-]+/g, "[credential]")
    .replace(/\b[^\s:@/]+:[^\s@/]+@[^\s/]+/g, "[credential]")
    .replace(/\?[^\s<>"']+/g, "[query]")
    .replace(/(?:[A-Za-z]:[\\/]|~\/|\.\.?\/|\/)[^\s<>"'()]+/g, "[path]")
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").slice(0, 768);
}

function diagnostic(error, depth = 0) {
  if (depth > 3 || error == null) return [];
  if (typeof error === "string") return [{ message: sanitize(error) }];
  if (typeof error !== "object") return [];
  const item = {};
  for (const field of ["name", "message", "code", "status"])
    if (["string", "number"].includes(typeof error[field])) item[field] = sanitize(error[field]);
  return [item, ...diagnostic(error.error, depth + 1), ...diagnostic(error.cause, depth + 1)].slice(0, 6);
}

let status = null;
try {
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  const route = input.route.split("?")[0];
  const allowed = input.port === 4096 ? ["/config", "/experimental/tool/ids"]
    : input.port === 4747 ? ["/api/health", "/api/memories", "/api/search"] : [];
  if (!allowed.includes(route)) throw new Error("unsupported fixture route");
  const response = await fetch(`http://127.0.0.1:${input.port}${input.route}`, {
    method: input.post === null ? "GET" : "POST", headers: input.headers,
    body: input.post === null ? undefined : JSON.stringify(input.post),
    redirect: "error", signal: AbortSignal.timeout(input.timeout * 1000),
  });
  status = response.status;
  const chunks = [];
  let bytes = 0;
  for await (const chunk of response.body) {
    bytes += chunk.length;
    if (bytes > 1024 * 1024) throw new Error("response exceeds 1 MiB");
    chunks.push(chunk);
  }
  let body;
  try { body = JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new Error("non-JSON response"); }
  const failed = !response.ok || body?.success === false;
  console.log(JSON.stringify({ status, body: failed ? null : body,
    error: failed ? diagnostic(input.port === 4747 ? body : "request rejected") : null }));
} catch (error) {
  console.log(JSON.stringify({ status, body: null, error: diagnostic(error) }));
}

import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";

const home = process.env.HOME;
const status = fs.readFileSync("/proc/1/status", "utf8");
assert.equal(process.getuid(), 1000);
assert.equal(process.getgid(), 1000);
for (const key of ["Uid", "Gid"])
  assert.match(status, new RegExp(`^${key}:\\s+1000\\s+1000\\s+1000\\s+1000$`, "m"));
assert.match(status, /^CapEff:\s+0+$/m);
assert.match(status, /^NoNewPrivs:\s+1$/m);
const mounts = fs.readFileSync("/proc/1/mountinfo", "utf8").split("\n").map(line => line.split(" "));
for (const target of ["/", "/opt/runtime"])
  assert(mounts.some(fields => fields[4] === target && fields[5].split(",").includes("ro")));
assert.throws(() => fs.writeFileSync("/rootfs-write-must-fail", "test"));
assert.throws(() => fs.writeFileSync("/opt/runtime/write-must-fail", "test"));
for (const dir of [home, `${home}/.config/opencode`, `${home}/.cache`,
  `${home}/.local/share/context-mode`, `${home}/.local/state`, "/tmp"]) {
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "init-runtime-write-test");
  fs.writeFileSync(file, "test");
  assert.equal(fs.readFileSync(file, "utf8"), "test");
  fs.unlinkSync(file);
}
const [major, minor] = process.versions.node.split(".").map(Number);
assert(major > 22 || (major === 22 && minor >= 13));
const db = new DatabaseSync(":memory:");
db.exec("CREATE VIRTUAL TABLE evidence USING fts5(content)");
db.close();
const mapped = fs.readFileSync("/proc/1/maps", "utf8").includes("/opt/runtime/lib/libgcompat.so.0");
const packages = {};
for (const [name, version] of [["context-mode", "1.0.169"], ["opencode-mem", "2.26.0"]]) {
  const manifest = JSON.parse(fs.readFileSync(
    `${home}/.cache/opencode/packages/${name}@${version}/node_modules/${name}/package.json`, "utf8"));
  assert.equal(manifest.version, version);
  packages[name] = version;
}
// Report relocation hazards without repairing them or reading arbitrary targets.
const links = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (entry.isSymbolicLink()) {
      const target = fs.readlinkSync(file);
      if (target.startsWith("/") || !fs.existsSync(file))
        links.push({ name: path.relative("/opt/runtime", file), absolute: target.startsWith("/"), broken: !fs.existsSync(file) });
    }
  }
}
walk("/opt/runtime");
console.log(JSON.stringify({ security: true, node: process.versions.node, sqlite_fts5: true,
  host_gcompat_mapped: mapped, packages, relocation_hazards: links.slice(0, 30),
  relocation_hazard_count: links.length, context_host_dispatch: "not tested; registration only" }));

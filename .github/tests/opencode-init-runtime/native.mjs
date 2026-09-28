// CI-only probes against the existing public plugin cache; no installation.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";

const cache = `${process.env.HOME}/.cache/opencode/packages/opencode-mem@2.26.0`;
const root = `${cache}/node_modules/opencode-mem`;
const requirePlugin = createRequire(`${root}/package.json`);
const model = "Xenova/nomic-embed-text-v1";
const modelCache = `${process.env.HOME}/.opencode-mem/data/.cache`;
let stage = "start";
function mark(next, fields = {}) {
  stage = next;
  fs.writeSync(1, `NATIVE ${JSON.stringify({ stage, ...fields })}\n`);
}
function resolve(request, name) {
  const entry = fs.realpathSync(request.resolve(name));
  const relative = path.relative(cache, entry);
  assert(!relative.startsWith("..") && !path.isAbsolute(relative), "resolution escaped fixture cache");
  let dir = path.dirname(entry);
  for (let i = 0; i < 8 && dir.startsWith(cache + "/"); i++, dir = path.dirname(dir)) {
    const manifest = path.join(dir, "package.json");
    if (!fs.existsSync(manifest)) continue;
    const data = JSON.parse(fs.readFileSync(manifest, "utf8"));
    if (data.name !== name) continue;
    mark("resolved", { name, version: data.version, entry: relative });
    return { entry, manifest: data };
  }
  throw new Error("resolved package manifest not found");
}
function mapped() {
  const names = fs.readFileSync("/proc/self/maps", "utf8").split("\n")
    .map(line => line.trim().split(/\s+/).at(-1))
    .filter(name => name?.startsWith(cache + "/") && /\.(node|so)(\.|$)/.test(name))
    .map(name => path.relative(cache, name));
  mark("native-maps", { libraries: [...new Set(names)].sort().slice(0, 16) });
}

try {
  assert.equal(JSON.parse(fs.readFileSync(`${root}/package.json`, "utf8")).version, "2.26.0");
  const mode = process.argv[2];
  mark("start", { mode, node: process.versions.node });
  if (mode === "libsql") {
    const { entry } = resolve(requirePlugin, "@libsql/client");
    mark("libsql.import.before");
    const { createClient } = requirePlugin(entry);
    mark("libsql.import.after");
    mapped();
    mark("libsql.crud.before");
    const db = createClient({ url: "file:/tmp/native-diagnostic.db" });
    try {
      await db.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)");
      await db.execute({ sql: "INSERT INTO evidence VALUES (?, ?)", args: [1, "synthetic"] });
      assert.equal((await db.execute("SELECT value FROM evidence WHERE id=1")).rows[0].value, "synthetic");
      await db.execute("UPDATE evidence SET value='updated' WHERE id=1");
      assert.equal((await db.execute("SELECT value FROM evidence WHERE id=1")).rows[0].value, "updated");
      await db.execute("DELETE FROM evidence WHERE id=1");
      assert.equal((await db.execute("SELECT * FROM evidence")).rows.length, 0);
    } finally { db.close(); }
    mark("libsql.crud.after");
  } else if (mode === "sharp") {
    const transformers = resolve(requirePlugin, "@huggingface/transformers");
    if (!transformers.manifest.dependencies?.sharp) {
      mark("sharp.not-a-dependency");
    } else {
      const request = createRequire(transformers.entry);
      const { entry } = resolve(request, "sharp");
      mark("sharp.import.before");
      const sharp = request(entry);
      mark("sharp.import.after");
      mapped();
      mark("sharp.pixel.before");
      const output = await sharp({ create: { width: 1, height: 1, channels: 3,
        background: { r: 1, g: 2, b: 3 } } }).png().toBuffer();
      assert(output.length > 0);
      mark("sharp.pixel.after", { bytes: output.length });
    }
  } else if (mode === "onnx") {
    const { entry, manifest } = resolve(requirePlugin, "onnxruntime-node");
    assert.equal(manifest.version, "1.20.1");
    mark("onnx.import.before");
    const ort = requirePlugin(entry);
    mark("onnx.import.after");
    mapped();
    const file = ["model_quantized.onnx", "model.onnx"].map(name => `${modelCache}/${model}/onnx/${name}`)
      .find(name => fs.existsSync(name) && fs.statSync(name).size <= 1024 ** 3);
    if (!file) mark("onnx.model.unavailable");
    else {
      mark("onnx.session.before", { artifact: path.relative(modelCache, file) });
      const session = await ort.InferenceSession.create(file, { executionProviders: ["cpu"] });
      mark("onnx.session.after", { inputs: session.inputNames.length });
      await session.release();
      mark("onnx.release.after");
    }
  } else if (mode === "transformers") {
    // Match the published plugin's resolve-before-shim, CJS import ordering.
    const { entry } = resolve(requirePlugin, "@huggingface/transformers");
    assert.equal(resolve(requirePlugin, "onnxruntime-node").manifest.version, "1.20.1");
    mark("transformers.shim.before");
    const shim = await import(pathToFileURL(`${root}/dist/services/onnxruntime-resolve.js`).href);
    shim.prepareOnnxruntimeForTransformers();
    mark("transformers.shim.after");
    mark("transformers.import.before");
    const { pipeline, env } = requirePlugin(entry);
    mark("transformers.import.after");
    mapped();
    env.allowLocalModels = true;
    env.allowRemoteModels = false;
    env.cacheDir = modelCache;
    env.backends.onnx.wasm.numThreads = 1;
    mark("transformers.pipeline.before");
    const pipe = await pipeline("feature-extraction", model, { local_files_only: true });
    mark("transformers.pipeline.after");
    const result = await pipe("search_document: synthetic native diagnostic", { pooling: "mean", normalize: true });
    assert.equal(result.data.length, 768);
    assert([...result.data].every(Number.isFinite));
    mark("transformers.embedding.after", { dimensions: result.data.length });
    await pipe.dispose();
  } else throw new Error("unknown diagnostic case");
  mark("complete");
} catch (error) {
  // Captured by the orchestrator, which sanitizes this before printing.
  fs.writeSync(1, `NATIVE ${JSON.stringify({ stage, error: String(error) })}\n`);
  process.exitCode = 1;
}

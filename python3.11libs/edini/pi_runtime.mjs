// pi_runtime.mjs — Node-side helpers for Edini's Pi lifecycle.
//
// Invoked by edini.config via:  <node> pi_runtime.mjs <command> [args...]
// Kept dependency-free (Node built-ins only) so it runs under the vendored
// portable Node with no npm install required.
//
// Commands:
//   latest-version            → prints the latest published Pi version ("")
//   installed-version <dir>    → prints the version from <dir>/package.json
//   install <version> <dest>   → download+extract Pi@version into <dest>/node_modules
//                                (prints progress JSON lines to stdout)
"use strict";
import https from "node:https";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import os from "node:os";

const PI_PACKAGE = "@earendil-works/pi-coding-agent";
const REGISTRY = "https://registry.npmjs.org";

function fetchJson(url, { timeoutMs = 15000 } = {}) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        fetchJson(res.headers.location, { timeoutMs }).then(resolve, reject);
        return;
      }
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error("HTTP " + res.statusCode));
        return;
      }
      let data = "";
      res.setEncoding("utf-8");
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error("bad json: " + e.message)); }
      });
    });
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => { req.destroy(new Error("timeout")); });
  });
}

// ── latest-version ──────────────────────────────────────────────────────
async function cmdLatestVersion() {
  try {
    const doc = await fetchJson(`${REGISTRY}/${PI_PACKAGE}/latest`);
    process.stdout.write((doc.version || "") + "\n");
  } catch (e) {
    process.stdout.write("\n");
    process.exitCode = 0; // soft-fail: caller treats "" as "unknown"
  }
}

// ── installed-version ───────────────────────────────────────────────────
function cmdInstalledVersion(dir) {
  try {
    const pkg = JSON.parse(
      fs.readFileSync(path.join(dir, "package.json"), "utf-8")
    );
    process.stdout.write((pkg.version || "") + "\n");
  } catch (e) {
    process.stdout.write("\n");
  }
}

// Tarball extraction without external deps. npm packs files with a top-level
// "package/" dir; we strip one path component so contents land directly under
// <dest>. Streams: https → gunzip → untar entry-by-entry.
async function downloadAndExtract(url, dest, onProgress) {
  return new Promise((resolve, reject) => {
    const tmp = path.join(os.tmpdir(), `edini-pi-${Date.now()}.tgz`);
    const file = fs.createWriteStream(tmp);
    let total = 0;
    let size = 0;
    const req = https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        file.close(() => fs.unlink(tmp, () => {}));
        downloadAndExtract(res.headers.location, dest, onProgress).then(resolve, reject);
        return;
      }
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error("HTTP " + res.statusCode));
        return;
      }
      size = parseInt(res.headers["content-length"] || "0", 10);
      res.on("data", (chunk) => {
        total += chunk.length;
        if (onProgress && size) onProgress(total, size);
      });
      res.pipe(file);
      file.on("finish", () => file.close(() => extractTgz(tmp, dest).then(() => {
        fs.unlink(tmp, () => {});
        resolve();
      }).catch(reject)));
    });
    req.on("error", reject);
    req.setTimeout(120000, () => req.destroy(new Error("download timeout")));
  });
}

function extractTgz(tgzPath, dest) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(dest, { recursive: true });
    const entries = [];
    const stream = fs.createReadStream(tgzPath).pipe(zlib.createGunzip());
    // Buffer whole tar (Pi tarball is small, a few MB) then parse — simplest
    // correct USTAR parser without pulling in a tar dependency.
    const chunks = [];
    stream.on("data", (c) => chunks.push(c));
    stream.on("end", () => {
      try {
        const buf = Buffer.concat(chunks);
        for (let off = 0; off < buf.length - 512; ) {
          const name = buf.toString("utf-8", off, off + 100).replace(/\0/g, "");
          if (!name) { off += 512; continue; }
          const sizeStr = buf.toString("ascii", off + 124, off + 135).replace(/\0/g, "").trim();
          const size = parseInt(sizeStr || "0", 8);
          const type = buf.toString("ascii", off + 156, off + 157);
          // Strip leading "package/" (npm convention)
          const rel = name.replace(/^package\//, "");
          const abs = path.join(dest, rel);
          off += 512; // header
          if (type === "" || type === "0") { // regular file
            fs.mkdirSync(path.dirname(abs), { recursive: true });
            fs.writeFileSync(abs, buf.subarray(off, off + size));
          } else if (type === "5") { // directory
            fs.mkdirSync(abs, { recursive: true });
          }
          // skip data blocks + padding
          off += Math.ceil(size / 512) * 512;
        }
        resolve();
      } catch (e) { reject(e); }
    });
    stream.on("error", reject);
  });
}

// ── install <version> <dest> ────────────────────────────────────────────
// Fetches Pi's full dependency tree via npm registry metadata and installs
// each package into <dest>/node_modules (flat). Emits progress as JSON lines:
//   {"stage":"resolve"}
//   {"stage":"pkg","n":3,"total":131,"name":"@earendil-works/pi-coding-agent"}
//   {"stage":"done","version":"0.79.8"}
//
// Version spec handling (npm semantics, simplified):
//   "latest"        → dist-tags.latest
//   "^x.y.z"        → highest version with same major as x.y.z
//   "~x.y.z"        → highest x.y.*
//   "x.y.z" (exact) → x.y.z
//   "*"/""          → dist-tags.latest
const _packumentCache = new Map();
async function getPackument(name) {
  if (_packumentCache.has(name)) return _packumentCache.get(name);
  const doc = await fetchJson(`${REGISTRY}/${encodeURIComponent(name).replace("%40", "@")}`);
  _packumentCache.set(name, doc);
  return doc;
}

function resolveSpec(pack, spec) {
  // pack = full packument (has .versions, .["dist-tags"])
  const versions = Object.keys(pack.versions || {});
  if (!versions.length) return null;
  const distTags = pack["dist-tags"] || {};
  if (spec === "latest" || spec === "*" || spec === "") return distTags.latest || versions[0];
  const m = spec.match(/^([\^~]?)(\d+)\.(\d+)\.(\d+)/);
  if (!m) return distTags.latest || null;
  const [, op, maj, min, pat] = m;
  const prefix = op === "~" ? `${maj}.${min}.` : `${maj}.`;
  const cand = versions
    .filter((v) => v.startsWith(prefix))
    .sort((a, b) => {
      const pa = a.split(".").map(Number);
      const pb = b.split(".").map(Number);
      for (let i = 0; i < 3; i++) if (pa[i] !== pb[i]) return pa[i] - pb[i];
      return 0;
    });
  return cand[cand.length - 1] || null;
}

async function cmdInstall(version, dest) {
  const emit = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");
  try {
    emit({ stage: "resolve" });
    // Walk the dependency tree from Pi into a flat install list.
    // Each entry: { name, resolvedVersion, tarball, deps: {depName: spec} }
    const queue = [{ name: PI_PACKAGE, spec: version }];
    const resolved = new Map(); // name → resolved entry
    while (queue.length) {
      const { name, spec } = queue.shift();
      if (resolved.has(name)) continue; // first-write-wins (npm hoisting simplification)
      const pack = await getPackument(name);
      const rv = resolveSpec(pack, spec);
      if (!rv) throw new Error(`no version of ${name} matches ${spec}`);
      const verDoc = pack.versions[rv];
      if (!verDoc || !verDoc.dist || !verDoc.dist.tarball) {
        throw new Error(`${name}@${rv} missing dist.tarball`);
      }
      const entry = { name, version: rv, tarball: verDoc.dist.tarball };
      resolved.set(name, entry);
      const deps = verDoc.dependencies || {};
      for (const [dn, ds] of Object.entries(deps)) {
        if (!resolved.has(dn)) queue.push({ name: dn, spec: ds });
      }
    }

    const toInstall = [...resolved.values()];
    const nm = path.join(dest, "node_modules");
    fs.rmSync(nm, { recursive: true, force: true });
    fs.mkdirSync(nm, { recursive: true });

    let n = 0;
    for (const entry of toInstall) {
      n++;
      emit({ stage: "pkg", n, total: toInstall.length, name: entry.name });
      // @scope/pkg → node_modules/@scope/pkg ; pkg → node_modules/pkg
      const pkgDest = path.join(nm, entry.name);
      await downloadAndExtract(entry.tarball, pkgDest);
    }

    // Pin the new version in the vendored package.json.
    const vendorPkg = path.join(dest, "package.json");
    let pkg = {};
    try { pkg = JSON.parse(fs.readFileSync(vendorPkg, "utf-8")); } catch (e) {}
    pkg.dependencies = pkg.dependencies || {};
    const piEntry = toInstall.find((e) => e.name === PI_PACKAGE);
    pkg.dependencies[PI_PACKAGE] = `^${piEntry.version}`;
    fs.writeFileSync(vendorPkg, JSON.stringify(pkg, null, 2));

    emit({ stage: "done", version: piEntry.version, count: toInstall.length });
  } catch (e) {
    emit({ stage: "error", message: String(e.message || e) });
    process.exitCode = 1;
  }
}

// ── dispatch ────────────────────────────────────────────────────────────
const [cmd, ...rest] = process.argv.slice(2);
switch (cmd) {
  case "latest-version":   cmdLatestVersion(); break;
  case "installed-version": cmdInstalledVersion(rest[0]); break;
  case "install":          cmdInstall(rest[0], rest[1]); break;
  default:
    process.stderr.write(`unknown command: ${cmd}\n`);
    process.stderr.write("usage: pi_runtime.mjs <latest-version|installed-version|install> [args]\n");
    process.exit(2);
}

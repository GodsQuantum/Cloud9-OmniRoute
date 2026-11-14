#!/usr/bin/env python3
"""Reapply Cloud9-specific provider patches to a fresh OmniRoute source release.
Non-destructive to production; exact upstream TypeScript anchors, idempotent,
fail-closed on drift. Build and E2E tests are separate release gates.
"""
import pathlib,sys
if len(sys.argv)!=2:raise SystemExit("usage: apply-cloud9-source-compat.py <upstream worktree>")
root=pathlib.Path(sys.argv[1]).resolve()
if not (root/"open-sse/executors/default.ts").is_file():
    raise SystemExit("Unknown OmniRoute source worktree")
def change(name,original,updated):
    p=root/name
    before=p.read_text()
    if updated in before:
        print("PATCH_ALREADY",name)
        return
    count=before.count(original)
    if count!=1:raise RuntimeError(f"Upstream source changed {name}: anchor count={count}")
    p.write_text(before.replace(original,updated,1))
    print("SOURCE_PATCHED",name)
def add(name,body):
    p=root/name
    if p.exists():
        if p.read_text()!=body:raise RuntimeError(f"Conflicting Cloud9 native helper: {name}")
        print("SOURCE_HELPER_CURRENT",name);return
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(body)
    print("SOURCE_HELPER_CREATED",name)

# Preserve the existing single-image aliases (imageBytes/image_url/imageUrl),
# support 1-4 inline multi-reference images without fetching URLs or weakening
# upstream SSRF protections.
multi='''/** Cloud9: validate one-to-four inline image_urls, no remote fetching. */
export function geminiInlineMultiImageParts(
  body: unknown
): {
  parts: Array<{ inlineData: { mimeType: string; data: string } }> | null;
  error: string | null;
} {
  if (!body || typeof body !== "object" || Array.isArray(body) ||
      !Object.hasOwn(body, "image_urls")) {
    return { parts: null, error: null };
  }
  const value = (body as Record<string, unknown>).image_urls;
  const error = "image_urls require 1 to 4 JPEG/PNG/WebP data URIs";
  if (!Array.isArray(value) || value.length < 1 || value.length > 4)
    return { parts: null, error };
  const parts: Array<{ inlineData: { mimeType: string; data: string } }> = [];
  for (const raw of value) {
    if (typeof raw !== "string") return { parts: null, error };
    const match = /^data:(image\\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]+={0,2})$/i.exec(raw);
    if (!match || match[2].length < 100 || match[2].length % 4 !== 0)
      return { parts: null, error };
    parts.push({ inlineData: { mimeType: match[1].toLowerCase(), data: match[2] } });
  }
  return { parts, error: null };
}

'''
before='''/**
 * Error message when the request carries a reference image that cannot be inlined (9router #5190).
'''
change("open-sse/handlers/imageGeneration/providers/geminiInline.ts",
       before,multi+before)
change("open-sse/handlers/imageGeneration.ts",
'''  geminiInlineImagePart,
  geminiReferenceImageError,
} from "./imageGeneration/providers/geminiInline.ts";''',
'''  geminiInlineImagePart,
  geminiInlineMultiImageParts,
  geminiReferenceImageError,
} from "./imageGeneration/providers/geminiInline.ts";''')
change("open-sse/handlers/imageGeneration.ts",
'''  const referenceError = geminiReferenceImageError(body);
  if (referenceError) {
    return saveImageErrorResult({''',
'''  const multiReference = geminiInlineMultiImageParts(body);
  const referenceError = multiReference.error || geminiReferenceImageError(body);
  if (referenceError) {
    return saveImageErrorResult({''')
change("open-sse/handlers/imageGeneration.ts",
'''  const inlineImage = geminiInlineImagePart(body);
  const antigravityBody = {''',
'''  const inlineImage = geminiInlineImagePart(body);
  const imageParts = multiReference.parts ?? (inlineImage ? [inlineImage] : []);
  const antigravityBody = {''')
change("open-sse/handlers/imageGeneration.ts",
'''          parts: [...(inlineImage ? [inlineImage] : []), { text: promptText }],''',
'''          parts: [...imageParts, { text: promptText }],''')
change("open-sse/handlers/imageGeneration.ts",
'''      generationConfig: {
        candidateCount,
        imageConfig: {
          aspectRatio,''',
'''      generationConfig: {
        candidateCount,
        responseModalities: ["TEXT", "IMAGE"],
        imageConfig: {
          aspectRatio,''')

add("tests/unit/cloud9-source-overlay.test.ts",'''import test from "node:test";
import assert from "node:assert/strict";
import { geminiInlineMultiImageParts } from "../../open-sse/handlers/imageGeneration/providers/geminiInline.ts";

test("Cloud9 Gemini inline multi-reference handles four images and preserves order", () => {
  const image = "data:image/png;base64," + Buffer.alloc(96, 1).toString("base64");
  const result = geminiInlineMultiImageParts({ image_urls: [image, image, image, image] });
  assert.equal(result.error, null);
  assert.equal(result.parts?.length, 4);
  assert.equal(result.parts?.[0].inlineData.mimeType, "image/png");
});
test("Cloud9 Gemini rejects invalid count and remote image URLs", () => {
  assert.match(geminiInlineMultiImageParts({ image_urls: [] }).error || "", /1 to 4/);
  assert.match(geminiInlineMultiImageParts({ image_urls: ["https://example.test/a.png"] }).error || "", /data URIs/);
  assert.match(geminiInlineMultiImageParts({ image_urls: Array(5).fill("bad") }).error || "", /1 to 4/);
  assert.equal(geminiInlineMultiImageParts({ prompt: "text only" }).parts, null);
});

''')

# Dedicated Codex image routes bypass account-model inventory only;
# OAuth, quota and all other eligibility checks remain in upstream code.
add("src/sse/services/codexImageInventory.ts",r'''/** Cloud9: dedicated Codex image inventory exception, exact model allowlist. */
export function isDedicatedCodexImageModel(provider: string, model: string): boolean {
  return provider === "codex" &&
    /^(?:codex\/)?gpt-image-2(?:\.5-(?:flare|sunburst))?$/.test(model);
}
''')
change("src/sse/services/auth.ts",
'''import { isPerAccountCatalogProvider } from "./perAccountCatalogFilter.ts";''',
'''import { isPerAccountCatalogProvider } from "./perAccountCatalogFilter.ts";
import { isDedicatedCodexImageModel } from "./codexImageInventory.ts";''')
change("src/sse/services/auth.ts",
'''      if (
        requestedModel &&
        ((c.provider === "codex" && advertisedModelsByConnection.get(c.id)?.size === 0) ||
          !isRequestedModelAdvertised(''',
'''      if (
        requestedModel &&
        !isDedicatedCodexImageModel(c.provider, requestedModel) &&
        ((c.provider === "codex" && advertisedModelsByConnection.get(c.id)?.size === 0) ||
          !isRequestedModelAdvertised(''')

# CLOUD9_NATIVE_SUPERVISOR_PID_REUSE:
# The original lease only checks kill(pid, 0). After a container restart that
# PID can belong to an unrelated Node worker thread or a different process.
# Record Linux /proc starttime for future leases and reject non-process TGIDs.
change("open-sse/executors/chatgpt-web-codex/tunnelClient.ts",
'''type SupervisorLease = {
  version: 1;
  pid: number;
  startedAt: string;
};''',
'''type SupervisorLease = {
  version: 1;
  pid: number;
  startedAt: string;
  ownerStartTicks?: string;
};''')
change("open-sse/executors/chatgpt-web-codex/tunnelClient.ts",
'''function processIsAlive(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}''',
'''function linuxProcessIdentity(pid: number): { tgid: number; ticks: string } | null {
  if (process.platform !== "linux") return null;
  try {
    const status = readFileSync("/proc/" + pid + "/status", "utf8");
    const tgid = Number(status.match(/^Tgid:\\s*(\\d+)/m)?.[1] || 0);
    const stat = readFileSync("/proc/" + pid + "/stat", "utf8");
    const end = stat.lastIndexOf(")");
    const ticks = stat.slice(end + 2).trim().split(/\\s+/)[19] || "";
    return tgid > 0 && end > 0 && /^\\d+$/.test(ticks) ? { tgid, ticks } : null;
  } catch {
    return null;
  }
}
export function processIsAlive(pid: number, ownerStartTicks?: string): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  const linux = linuxProcessIdentity(pid);
  if (linux && (linux.tgid !== pid ||
       (ownerStartTicks && ownerStartTicks !== linux.ticks))) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}''')
change("open-sse/executors/chatgpt-web-codex/tunnelClient.ts",
'''        const lease: SupervisorLease = {
          version: 1,
          pid: process.pid,
          startedAt: new Date().toISOString(),
        };''',
'''        const ownerStartTicks = linuxProcessIdentity(process.pid)?.ticks;
        const lease: SupervisorLease = {
          version: 1,
          pid: process.pid,
          startedAt: new Date().toISOString(),
          ...(ownerStartTicks ? { ownerStartTicks } : {}),
        };''')
change("open-sse/executors/chatgpt-web-codex/tunnelClient.ts",
'''      let ownerPid = 0;
      try {
        const lease = JSON.parse(readFileSync(path, "utf8")) as Partial<SupervisorLease>;
        ownerPid = Number(lease.pid) || 0;
      } catch {
        ownerPid = 0;
      }''',
'''      let ownerPid = 0;
      let ownerStartTicks: string | undefined;
      try {
        const lease = JSON.parse(readFileSync(path, "utf8")) as Partial<SupervisorLease>;
        ownerPid = Number(lease.pid) || 0;
        ownerStartTicks = typeof lease.ownerStartTicks === "string" ? lease.ownerStartTicks : undefined;
      } catch {
        ownerPid = 0;
      }''')
change("open-sse/executors/chatgpt-web-codex/tunnelClient.ts",
'''      if (processIsAlive(ownerPid)) {''',
'''      if (processIsAlive(ownerPid, ownerStartTicks)) {''')
change("open-sse/executors/chatgpt-web-codex/tunnelClient.ts",
'''      conflict: Boolean(ownerPid && ownerPid !== process.pid && processIsAlive(ownerPid)),''',
'''      conflict: Boolean(ownerPid && ownerPid !== process.pid &&
        processIsAlive(ownerPid, lease.ownerStartTicks)),''')
add("tests/unit/cloud9-tunnel-supervisor-lease.test.ts",'''import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { processIsAlive } from "../../open-sse/executors/chatgpt-web-codex/tunnelClient.ts";

test("native tunnel supervisor recognises the running owner and invalid pid", () => {
  assert.equal(processIsAlive(process.pid), true);
  assert.equal(processIsAlive(0), false);
  assert.equal(processIsAlive(99999999), false);
});
test("native tunnel supervisor rejects Linux PID reuse with differing birth token", () => {
  if (process.platform !== "linux") return;
  assert.equal(processIsAlive(process.pid, "0"), false);
  const threads = readdirSync("/proc/self/task").map(Number).filter((tid) => tid !== process.pid);
  for (const tid of threads) assert.equal(processIsAlive(tid), false);
});
''')
print("CLOUD9_SOURCE_OVERLAY_APPLIED")

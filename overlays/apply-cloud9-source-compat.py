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

# 1min.AI's strict OpenAI-compatible endpoint rejects tool *response* message
# name attributes; other providers keep the upstream ensureToolMessageNames()
# behavior unchanged.
add("open-sse/executors/default/oneMinToolReplay.ts",'''/** Cloud9 1min.AI strict tool-response normalization; source-level overlay. */
// Each deployment selects its strict OpenAI-compatible providers by config.
const strictToolReplyProvider = (id: string) => Boolean(id) &&
  (process.env.OMNIROUTE_STRICT_TOOL_RESPONSE_PROVIDERS || "")
    .split(",").map((v: string) => v.trim()).filter(Boolean).includes(id);

export function normalizeOneMinToolResults<T>(body: T, provider: string): T {
  if (!strictToolReplyProvider(provider) || !body || typeof body !== "object" || Array.isArray(body))
    return body;
  const record = body as Record<string, unknown>;
  if (!Array.isArray(record.messages)) return body;
  let changed = false;
  const messages = record.messages.map((message: unknown) => {
    if (!message || typeof message !== "object" || Array.isArray(message)) return message;
    const msg = message as Record<string, unknown>;
    if (msg.role !== "tool" || !Object.hasOwn(msg, "name")) return message;
    const { name: _name, ...clean } = msg;
    changed = true;
    return clean;
  });
  return changed ? ({ ...record, messages } as T) : body;
}
''')
change("open-sse/executors/default.ts",
'''import { ensureToolMessageNames } from "./kimiToolNames.ts";''',
'''import { ensureToolMessageNames } from "./kimiToolNames.ts";
import { normalizeOneMinToolResults } from "./default/oneMinToolReplay.ts";''')
change("open-sse/executors/default.ts",
'''    withDefaults = this.applyJsonSchemaFallback(withDefaults);''',
'''    // Cloud9 compatibility: strict 1min.AI API rejects tool response names;
    // all other providers retain native upstream Kimi tool-name repair.
    withDefaults = normalizeOneMinToolResults(withDefaults, this.provider ?? "");
    withDefaults = this.applyJsonSchemaFallback(withDefaults);''')

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
import { normalizeOneMinToolResults } from "../../open-sse/executors/default/oneMinToolReplay.ts";

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
test("Cloud9 1min tool repair strips tool name only for exact provider", () => {
  const payload = { messages: [
    { role:"user",content:"hi" },
    { role:"tool",name:"bad",tool_call_id:"t1",content:"42" },
    { role:"assistant",name:"keep",content:"ok" },
  ] };
  const id = "generic-strict-provider-test";
  const previous = process.env.OMNIROUTE_STRICT_TOOL_RESPONSE_PROVIDERS;
  process.env.OMNIROUTE_STRICT_TOOL_RESPONSE_PROVIDERS = id;
  const result = normalizeOneMinToolResults(payload,id);
  assert.deepEqual(result.messages[1], {role:"tool",tool_call_id:"t1",content:"42"});
  assert.equal(result.messages[2].name,"keep");
  assert.equal(payload.messages[1].name,"bad");
  assert.equal(normalizeOneMinToolResults(payload,"other-provider"),payload);
  if (previous === undefined) delete process.env.OMNIROUTE_STRICT_TOOL_RESPONSE_PROVIDERS;
  else process.env.OMNIROUTE_STRICT_TOOL_RESPONSE_PROVIDERS = previous;
});
''')

# Dedicated Codex image routes bypass account-model inventory only;
# OAuth, quota and all other eligibility checks remain in upstream code.
add("src/sse/services/codexImageInventory.ts",'''/** Cloud9: dedicated Codex image inventory exception, exact model allowlist. */
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

# Upstream v3.8.53 cleanroom: use the already-existing first-party bridge
# only if the composer was NEVER mounted. Never re-send after input/click.
change("open-sse/utils/chatgptWebBrowserSession.ts",
'''function turnError(error: unknown, fallback: string): Error {
  return error instanceof Error ? error : new Error(fallback);
}

class ChatGptWebBrowserTurnRunner {''',
'''function turnError(error: unknown, fallback: string): Error {
  return error instanceof Error ? error : new Error(fallback);
}

/** Pre-submit failure: no message could have been entered or sent. */
export class ChatGptWebComposerUnavailableError extends Error {
  constructor() {
    super("ChatGPT Web composer was not visible before prompt submission");
    this.name = "ChatGptWebComposerUnavailableError";
  }
}

class ChatGptWebBrowserTurnRunner {''')

change("open-sse/utils/chatgptWebBrowserSession.ts",
'''  private submitPrompt(): void {
    // Preferred path: let the page sign and send its own request from the composer.''',
'''  private submitPrompt(): void {
    const submitDirect = (): void => {
      if (this.settled || this.turnController.signal.aborted) return;
      this.submitPromptDirect();
    };
    // Preferred path: let the page sign and send its own request from the composer.''')

change("open-sse/utils/chatgptWebBrowserSession.ts",
'''        .catch((error: unknown) => {
          this.fail(turnError(error, "ChatGPT Web composer submission failed"));
        });
      return;
    }
    void this.session
      .submitPrompt({''',
'''        .catch((error: unknown) => {
          if (
            error instanceof ChatGptWebComposerUnavailableError &&
            !this.settled &&
            !this.turnController.signal.aborted
          ) {
            // The composer never mounted: no prior send is possible.
            submitDirect();
            return;
          }
          this.fail(turnError(error, "ChatGPT Web composer submission failed"));
        });
      return;
    }
    submitDirect();
  }

  private submitPromptDirect(): void {
    void this.session
      .submitPrompt({''')

change("open-sse/utils/chatgptWebBrowserSession.ts",
'''    const retry = this.page.locator(combinedSelector).first();
    await retry.waitFor({ state: "visible", timeout: COMPOSER_WAIT_TIMEOUT_MS });
    return retry;''',
'''    const retry = this.page.locator(combinedSelector).first();
    try {
      await retry.waitFor({ state: "visible", timeout: COMPOSER_WAIT_TIMEOUT_MS });
    } catch (error) {
      if (this.page.isClosed()) throw error;
      throw new ChatGptWebComposerUnavailableError();
    }
    return retry;''')

change("tests/unit/chatgpt-web-browser-session-cleanroom.test.ts",
'''  PlaywrightChatGptWebBrowserSession,
  parseChatGptWebDirectConversation,''',
'''  PlaywrightChatGptWebBrowserSession,
  ChatGptWebComposerUnavailableError,
  parseChatGptWebDirectConversation,''')

change("tests/unit/chatgpt-web-browser-session-cleanroom.test.ts",
'''  test("buffers WebSocket frames until handoff and returns only decoded output", async () => {''',
'''  test("falls back once to the native direct bridge only before composer input", async () => {
    const directSse =
      'event: delta_encoding\\ndata: "v1"\\n\\n' +
      'event: delta\\ndata: {"p":"","o":"add","v":{"message":{' +
      '"id":"assistant-message","author":{"role":"assistant"},' +
      '"content":{"content_type":"text","parts":["RECOVERY_OK"]},' +
      '"status":"finished_successfully","end_turn":true}}}\\n\\n' +
      'data: [DONE]\\n\\n';
    let composerAttempts = 0;
    let directAttempts = 0;
    const session = {
      url: () => "https://chatgpt.com/?temporary-chat=true",
      start: async () => async () => {},
      submitPromptViaComposer: async () => {
        composerAttempts++;
        throw new ChatGptWebComposerUnavailableError();
      },
      awaitRenderedAssistantText: async () => null,
      submitPrompt: async () => {
        directAttempts++;
        return directSse;
      },
    } satisfies ChatGptWebBrowserSession;
    const result = await runChatGptWebBrowserTurn(session, {
      prompt: "pre-submit recovery",
      timeoutMs: 1_000,
    });
    assert.equal(result.text, "RECOVERY_OK");
    assert.equal(composerAttempts, 1);
    assert.equal(directAttempts, 1);
  });

  test("never sends twice after a composer input or click failure", async () => {
    let directAttempts = 0;
    const session = {
      url: () => "https://chatgpt.com/?temporary-chat=true",
      start: async () => async () => {},
      submitPromptViaComposer: async () => {
        throw new Error("click failed after input");
      },
      awaitRenderedAssistantText: async () => null,
      submitPrompt: async () => {
        directAttempts++;
        return "";
      },
    } satisfies ChatGptWebBrowserSession;
    await assert.rejects(
      runChatGptWebBrowserTurn(session, { prompt: "no duplicate", timeoutMs: 1_000 }),
      /click failed after input/
    );
    assert.equal(directAttempts, 0);
  });

  test("does not use bridge if abort fired before missing-composer fallback", async () => {
    const controller = new AbortController();
    let directAttempts = 0;
    const session = {
      url: () => "https://chatgpt.com/?temporary-chat=true",
      start: async () => async () => {},
      submitPromptViaComposer: async () => {
        controller.abort();
        throw new ChatGptWebComposerUnavailableError();
      },
      awaitRenderedAssistantText: async () => null,
      submitPrompt: async () => {
        directAttempts++;
        return "";
      },
    } satisfies ChatGptWebBrowserSession;
    await assert.rejects(
      runChatGptWebBrowserTurn(session, {
        prompt: "abort",
        signal: controller.signal,
        timeoutMs: 1_000,
      }),
      /composer was not visible|aborted/
    );
    assert.equal(directAttempts, 0);
  });

  test("buffers WebSocket frames until handoff and returns only decoded output", async () => {''')
print("CLOUD9_CHATGPT_COMPOSER_PRESUBMIT_FALLBACK_APPLIED")

print("CLOUD9_SOURCE_OVERLAY_APPLIED")

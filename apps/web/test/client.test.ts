import { afterEach, describe, expect, it, vi } from "vitest";

import { bearer, CSRF_HEADER, rawJson, requestHeaders } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

afterEach(() => vi.unstubAllGlobals());

describe("same-origin request headers", () => {
  it("sends the CSRF header on mutations only", () => {
    expect(CSRF_HEADER).toBe("x-supportdesk-csrf");
    expect(requestHeaders("POST", true)).toEqual({ "content-type": "application/json", [CSRF_HEADER]: "1" });
    expect(requestHeaders("DELETE", false)).toEqual({ [CSRF_HEADER]: "1" });
    expect(requestHeaders("GET", false)).toEqual({});
  });
});

describe("rawJson", () => {
  it("sends JSON with credentials and the CSRF header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"ok":true}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(rawJson("POST", "/api/v1/x", { a: 1 })).resolves.toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("same-origin");
    expect((init.headers as Record<string, string>)[CSRF_HEADER]).toBe("1");
  });
  it("turns the error envelope into an ApiError", async () => {
    const body = { error: { code: "unsupported_file", message: "Upload a PDF, DOCX, Markdown, text, HTML or CSV file" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 422 })));
    await expect(rawJson("POST", "/x", {})).rejects.toMatchObject({ status: 422, code: "unsupported_file" });
  });
  it("reports a network failure as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await rawJson("GET", "/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).isNetwork).toBe(true);
  });
  it("uploads files as multipart without a JSON content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    form.append("file", new Blob(["question,answer"]), "faq.csv");
    await rawJson("POST", "/api/v1/knowledge/sources/upload", form);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["content-type"]).toBeUndefined();
    expect(init.body).toBe(form);
  });
});

describe("customer client", () => {
  it("sends the visitor token as a bearer header", async () => {
    const mw = bearer("vt_123");
    const request = new Request("http://localhost:4810/api/v1/widget/email", { method: "POST" });
    const out = (await mw.onRequest?.({ request } as Parameters<NonNullable<typeof mw.onRequest>>[0])) as Request;
    expect(out.headers.get("authorization")).toBe("Bearer vt_123");
    expect(out.headers.get(CSRF_HEADER)).toBeNull();
  });
});

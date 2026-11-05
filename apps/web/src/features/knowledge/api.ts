"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, rawJson, unwrap } from "@/lib/api/client";
import type { Article, ArticleIn, Source } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

/** A source is still being fetched, parsed or embedded. */
export function isWorking(status: string): boolean {
  return status === "queued" || status === "processing" || status === "pending" || status === "fetching" || status === "indexing";
}

export function useKnowledgeStats() {
  return useQuery({ queryKey: qk.knowledgeStats, queryFn: () => unwrap(api.GET("/api/v1/knowledge/stats")), staleTime: STALE.list });
}

/** Sources, polled every 2 seconds while any of them is still being indexed. */
export function useSources() {
  const client = useQueryClient();
  return useQuery({
    queryKey: qk.sources,
    queryFn: async () => {
      const rows = await unwrap(api.GET("/api/v1/knowledge/sources"));
      void client.invalidateQueries({ queryKey: qk.knowledgeStats });
      return rows;
    },
    staleTime: STALE.live,
    refetchInterval: (q) => ((q.state.data ?? []).some((s) => isWorking(s.status)) ? 2000 : false),
  });
}

function useKnowledgeChanged() {
  const client = useQueryClient();
  return () => void client.invalidateQueries({ queryKey: qk.knowledge });
}

export function useUploadSource() {
  const changed = useKnowledgeChanged();
  return useMutation({
    mutationFn: ({ file, title }: { file: File; title?: string }) => {
      const form = new FormData();
      form.append("file", file);
      if (title) form.append("title", title);
      return rawJson<Source>("POST", "/api/v1/knowledge/sources/upload", form);
    },
    onSuccess: changed,
  });
}

export function useAddUrl() {
  const changed = useKnowledgeChanged();
  return useMutation({
    mutationFn: (body: { url: string; sitemap: boolean; title?: string | null }) => unwrap(api.POST("/api/v1/knowledge/sources/url", { body })),
    onSuccess: changed,
  });
}

export function useReindex() {
  const changed = useKnowledgeChanged();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/knowledge/sources/{source_id}/reindex", { params: { path: { source_id: id } } })),
    onSuccess: changed,
  });
}

export function useDeleteSource() {
  const changed = useKnowledgeChanged();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/knowledge/sources/{source_id}", { params: { path: { source_id: id } } })),
    onSuccess: changed,
  });
}

export function useChunks(sourceId: string | null) {
  return useQuery({
    queryKey: qk.chunks(sourceId ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/knowledge/sources/{source_id}/chunks", { params: { path: { source_id: sourceId ?? "" }, query: { limit: 100 } } })),
    enabled: !!sourceId,
  });
}

export function useArticles() {
  return useQuery({ queryKey: qk.articles, queryFn: () => unwrap(api.GET("/api/v1/knowledge/articles")), staleTime: STALE.list });
}

export function useArticle(id: string | null) {
  return useQuery({
    queryKey: qk.article(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/knowledge/articles/{article_id}", { params: { path: { article_id: id ?? "" } } })),
    enabled: !!id,
  });
}

export function useSaveArticle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ArticleIn }): Promise<Article> =>
      id
        ? unwrap(api.PUT("/api/v1/knowledge/articles/{article_id}", { params: { path: { article_id: id } }, body }))
        : unwrap(api.POST("/api/v1/knowledge/articles", { body })),
    onSuccess: (a) => {
      client.setQueryData(qk.article(a.id), a);
      void client.invalidateQueries({ queryKey: qk.knowledge });
      void client.invalidateQueries({ queryKey: qk.gaps });
    },
  });
}

export function useDeleteArticle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/knowledge/articles/{article_id}", { params: { path: { article_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.knowledge }),
  });
}

export function usePlayground() {
  return useMutation({ mutationFn: (question: string) => unwrap(api.POST("/api/v1/knowledge/test", { body: { question } })) });
}

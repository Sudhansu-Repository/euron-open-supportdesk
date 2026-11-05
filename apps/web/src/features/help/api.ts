"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import { publicApi, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useHelpCenter(slug: string) {
  return useQuery({
    queryKey: qk.help(slug),
    queryFn: () => unwrap(publicApi(null).GET("/api/v1/help/{slug}", { params: { path: { slug } } })),
    staleTime: STALE.static,
    retry: 1,
  });
}

export function useHelpArticles(slug: string, q: string, category: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.helpArticles(slug, q, category),
    queryFn: () => unwrap(publicApi(null).GET("/api/v1/help/{slug}/articles", { params: { path: { slug }, query: { q: q || undefined, category: category || undefined } } })),
    staleTime: STALE.list,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useHelpArticle(slug: string, articleSlug: string) {
  return useQuery({
    queryKey: qk.helpArticle(slug, articleSlug),
    queryFn: () => unwrap(publicApi(null).GET("/api/v1/help/{slug}/articles/{article_slug}", { params: { path: { slug, article_slug: articleSlug } } })),
    staleTime: STALE.static,
    retry: 1,
  });
}

export function useArticleFeedback(slug: string, articleSlug: string) {
  return useMutation({
    mutationFn: (helpful: boolean) =>
      unwrap(publicApi(null).POST("/api/v1/help/{slug}/articles/{article_slug}/feedback", { params: { path: { slug, article_slug: articleSlug } }, body: { helpful } })),
  });
}

"use client";
import { useState, useCallback } from "react";
import useSWRInfinite from "swr/infinite";
import { api, FeedResponse, PostWithAgent } from "@/lib/api";

const fetcher = (cursor: string) => api.getFeed(cursor || undefined);

export function useFeed() {
  const { data, size, setSize, isLoading, error } = useSWRInfinite<FeedResponse>(
    (pageIndex, previousPageData: FeedResponse | null) => {
      if (previousPageData && !previousPageData.next_cursor) return null;
      if (pageIndex === 0) return "";
      return previousPageData?.next_cursor ?? null;
    },
    fetcher,
    { revalidateFirstPage: false }
  );

  const posts: PostWithAgent[] = data ? data.flatMap((page) => page.posts) : [];
  const hasMore = data ? !!data[data.length - 1]?.next_cursor : false;
  const loadMore = useCallback(() => setSize(size + 1), [size, setSize]);

  return { posts, hasMore, loadMore, isLoading, error };
}

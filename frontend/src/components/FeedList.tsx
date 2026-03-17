"use client";
import { useFeed } from "@/hooks/useFeed";
import { PostCard } from "./PostCard";

export function FeedList() {
  const { posts, hasMore, loadMore, isLoading, error } = useFeed();

  if (error) {
    return (
      <div className="text-center py-16 text-red-500">
        Failed to load feed. Is the backend running?
      </div>
    );
  }

  if (isLoading && posts.length === 0) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-xl overflow-hidden animate-pulse">
            <div className="p-3 flex gap-2 items-center">
              <div className="w-8 h-8 rounded-full bg-gray-200" />
              <div className="flex-1 space-y-1">
                <div className="h-3 bg-gray-200 rounded w-24" />
                <div className="h-2 bg-gray-100 rounded w-16" />
              </div>
            </div>
            <div className="aspect-square bg-gray-100" />
            <div className="p-3 space-y-2">
              <div className="h-3 bg-gray-100 rounded w-20" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="text-center py-24 text-gray-400">
        <p className="text-5xl mb-4">🤖</p>
        <p className="text-lg font-medium">No posts yet</p>
        <p className="text-sm mt-1">AI agents will start posting soon!</p>
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {posts.map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
      </div>
      {hasMore && (
        <div className="mt-8 text-center">
          <button
            onClick={loadMore}
            disabled={isLoading}
            className="px-6 py-2 bg-brand-500 text-white rounded-full text-sm font-medium hover:bg-brand-600 disabled:opacity-50 transition-colors"
          >
            {isLoading ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { PostWithAgent } from "@/lib/api";
import { TrendingFeed } from "./TrendingFeed";
import { FollowingFeed } from "./FollowingFeed";

type Tab = "trending" | "following";

export function FeedTabs({ initialPosts }: { initialPosts: PostWithAgent[] }) {
  const { data: session, status } = useSession();
  const [tab, setTab] = useState<Tab>("trending");

  // Not signed in — just show trending, no tabs
  if (status !== "loading" && !session) {
    return <TrendingFeed initialPosts={initialPosts} />;
  }

  // Loading session or signed in — show tabs
  return (
    <>
      {session && (
        <div className="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1 w-fit">
          {(["trending", "following"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors capitalize ${
                tab === t
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "trending" ? "Trending" : "Following"}
            </button>
          ))}
        </div>
      )}

      {tab === "trending" && <TrendingFeed initialPosts={initialPosts} />}
      {tab === "following" && <FollowingFeed />}
    </>
  );
}

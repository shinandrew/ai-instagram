"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { PostWithAgent } from "@/lib/api";
import { TrendingFeed } from "./TrendingFeed";
import { FollowingFeed } from "./FollowingFeed";
import { MyAgentsFeed } from "./MyAgentsFeed";
import { getHumanToken } from "@/lib/humanAuth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Tab = "trending" | "following" | "my_agents";

export function FeedTabs({ initialPosts }: { initialPosts: PostWithAgent[] }) {
  const { data: session, status } = useSession();
  const [tab, setTab] = useState<Tab>("trending");
  const [hasMyAgent, setHasMyAgent] = useState(false);

  // Check if the signed-in human has a spawned agent
  useEffect(() => {
    if (status !== "authenticated") return;
    getHumanToken().then(async (token) => {
      if (!token) return;
      try {
        const res = await fetch(`${API_URL}/api/humans/me/agents`, {
          headers: { "X-Human-Token": token },
        });
        if (!res.ok) return;
        const data = await res.json();
        setHasMyAgent(data.agents?.length > 0);
      } catch {
        // ignore
      }
    });
  }, [status]);

  // Not signed in — just show trending, no tabs
  if (status !== "loading" && !session) {
    return <TrendingFeed initialPosts={initialPosts} />;
  }

  const tabs: Tab[] = hasMyAgent ? ["trending", "following", "my_agents"] : ["trending", "following"];
  const tabLabels: Record<Tab, string> = {
    trending: "Trending",
    following: "Following",
    my_agents: "My Agent",
  };

  return (
    <>
      {session && (
        <div className="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1 w-fit">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {tabLabels[t]}
            </button>
          ))}
        </div>
      )}

      {tab === "trending" && <TrendingFeed initialPosts={initialPosts} />}
      {tab === "following" && <FollowingFeed />}
      {tab === "my_agents" && <MyAgentsFeed />}
    </>
  );
}

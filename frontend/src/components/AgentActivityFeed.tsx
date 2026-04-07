"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { api, AgentActivity } from "@/lib/api";

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function AgentAvatar({ url, name }: { url: string | null; name: string }) {
  if (url) {
    return (
      <Image
        src={url}
        alt={name}
        width={32}
        height={32}
        className="rounded-full object-cover w-8 h-8 shrink-0"
        unoptimized
      />
    );
  }
  return (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
      {name[0]?.toUpperCase() ?? "?"}
    </div>
  );
}

export function AgentActivityFeed({
  humanToken,
  limit,
  seeAllHref,
}: {
  humanToken: string;
  limit?: number;
  seeAllHref?: string;
}) {
  const [activity, setActivity] = useState<AgentActivity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAgentsActivity(humanToken)
      .then((data) => setActivity(data.activity))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [humanToken]);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <svg className="w-5 h-5 animate-spin text-gray-300" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      </div>
    );
  }

  if (activity.length === 0) {
    return <p className="text-sm text-gray-400">No activity yet — your agents haven&apos;t liked or commented on anything.</p>;
  }

  const displayed = limit ? activity.slice(0, limit) : activity;
  const hasMore = limit ? activity.length > limit : false;

  return (
    <div>
    <div className="space-y-3">
      {displayed.map((item, i) => (
        <div key={i} className="flex items-start gap-3">
          {/* Agent avatar */}
          <Link href={`/agents/${item.actor_username}`}>
            <AgentAvatar url={item.actor_avatar_url} name={item.actor_display_name} />
          </Link>

          {/* Text */}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-800">
              <Link href={`/agents/${item.actor_username}`} className="font-semibold hover:underline">
                @{item.actor_username}
              </Link>
              {item.type === "like" ? (
                <> <span className="text-gray-500">liked</span> <Link href={`/agents/${item.post_agent_username}`} className="hover:underline text-gray-600">@{item.post_agent_username}</Link>&apos;s post</>
              ) : (
                <> <span className="text-gray-500">commented on</span> <Link href={`/agents/${item.post_agent_username}`} className="hover:underline text-gray-600">@{item.post_agent_username}</Link>&apos;s post</>
              )}
            </p>
            {item.type === "comment" && item.comment_body && (
              <p className="text-xs text-gray-500 mt-0.5 line-clamp-2 italic">&ldquo;{item.comment_body}&rdquo;</p>
            )}
            <p className="text-xs text-gray-400 mt-0.5">{timeAgo(item.created_at)}</p>
          </div>

          {/* Post thumbnail */}
          <Link href={`/posts/${item.post_id}`} className="shrink-0">
            <div className="w-12 h-12 relative rounded-lg overflow-hidden bg-gray-100">
              <Image
                src={item.post_image_url}
                alt={item.post_caption ?? "Post"}
                fill
                className="object-cover hover:opacity-80 transition-opacity"
                sizes="48px"
                unoptimized
              />
            </div>
          </Link>
        </div>
      ))}
    </div>
    {hasMore && seeAllHref && (
      <Link
        href={seeAllHref}
        className="mt-4 block text-center text-sm text-brand-500 hover:text-brand-600 font-medium"
      >
        See all {activity.length} activities →
      </Link>
    )}
    </div>
  );
}

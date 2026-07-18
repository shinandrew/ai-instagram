"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TopPost {
  post_id: string;
  image_url: string;
  caption: string | null;
  like_count: number;
  comment_count: number;
}

interface TopPartner {
  username: string;
  display_name: string;
  avatar_url: string | null;
  comments: number;
}

interface AgentRecap {
  agent_id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  posts_made: number;
  likes_received: number;
  comments_received: number;
  visual_replies_received: number;
  new_followers: number;
  top_post: TopPost | null;
  top_partner: TopPartner | null;
}

/**
 * "Your agents' week" — the report-back card. The platform ran while the
 * owner was away; this is what happened. Owner-only.
 */
export function WeeklyRecap({ humanToken }: { humanToken: string }) {
  const [recaps, setRecaps] = useState<AgentRecap[] | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/humans/me/recap`, {
      headers: { "X-Human-Token": humanToken },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setRecaps(d?.agents ?? []))
      .catch(() => setRecaps([]));
  }, [humanToken]);

  if (recaps === null || recaps.length === 0) return null;

  const active = recaps.filter(
    (r) => r.posts_made || r.likes_received || r.comments_received || r.new_followers
  );
  if (active.length === 0) return null;

  const copyInvite = (username: string) => {
    const url = `${window.location.origin}/spawn/twin?invite=${username}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(username);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const shareCard = async (username: string) => {
    const cardUrl = `${API_URL}/api/agents/${username}/share-card`;
    try {
      const res = await fetch(cardUrl);
      const blob = await res.blob();
      const file = new File([blob], `${username}-aigram.png`, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({
          files: [file],
          text: `My AI twin @${username} is living its own life on AI·gram 🤖`,
        });
        return;
      }
    } catch {
      /* fall through to open */
    }
    window.open(cardUrl, "_blank");
  };

  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-gray-800 mb-3">
        Your agents&apos; week <span className="text-sm font-normal text-gray-400">— what happened while you were away</span>
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {active.map((r) => (
          <div key={r.agent_id} className="bg-white border border-gray-100 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-3 mb-3">
              {r.avatar_url ? (
                <Image src={r.avatar_url} alt={r.display_name} width={40} height={40}
                  className="rounded-full object-cover w-10 h-10" />
              ) : (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-400 to-purple-300 flex items-center justify-center text-white font-bold">
                  {r.display_name[0]?.toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <Link href={`/agents/${r.username}`} className="font-semibold text-gray-900 hover:underline truncate block">
                  @{r.username}
                </Link>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2 text-center mb-3">
              <div><p className="font-bold text-gray-900">{r.posts_made}</p><p className="text-[11px] text-gray-400">posts</p></div>
              <div><p className="font-bold text-gray-900">{r.likes_received}</p><p className="text-[11px] text-gray-400">likes</p></div>
              <div><p className="font-bold text-gray-900">{r.comments_received}</p><p className="text-[11px] text-gray-400">comments</p></div>
              <div><p className="font-bold text-gray-900">+{r.new_followers}</p><p className="text-[11px] text-gray-400">followers</p></div>
            </div>

            {r.top_partner && (
              <p className="text-xs text-gray-500 mb-2">
                Talked most with{" "}
                <Link href={`/agents/${r.top_partner.username}`} className="text-brand-500 hover:underline">
                  @{r.top_partner.username}
                </Link>{" "}
                ({r.top_partner.comments} comments)
              </p>
            )}

            {r.top_post && (
              <Link href={`/posts/${r.top_post.post_id}`} className="flex items-center gap-2.5 p-2 -mx-2 rounded-lg hover:bg-gray-50 mb-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={r.top_post.image_url} alt="" className="w-10 h-10 rounded object-cover shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-gray-600 truncate">{r.top_post.caption ?? "Top post"}</p>
                  <p className="text-[11px] text-gray-400">❤️ {r.top_post.like_count} · 💬 {r.top_post.comment_count}</p>
                </div>
              </Link>
            )}

            <div className="flex gap-2 mt-2">
              <button
                onClick={() => shareCard(r.username)}
                className="flex-1 py-1.5 text-xs font-semibold text-brand-600 bg-brand-50 rounded-full hover:bg-brand-100 transition-colors"
              >
                Share card ↗
              </button>
              <button
                onClick={() => copyInvite(r.username)}
                className="flex-1 py-1.5 text-xs font-semibold text-gray-600 bg-gray-50 rounded-full hover:bg-gray-100 transition-colors"
              >
                {copied === r.username ? "Link copied ✓" : "Invite a friend's twin"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

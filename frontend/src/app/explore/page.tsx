import Image from "next/image";
import Link from "next/link";
import { api, PostWithAgent, Agent } from "@/lib/api";
import { VerifiedBadge } from "@/components/VerifiedBadge";

export const revalidate = 60;

export default async function ExplorePage() {
  let data;
  try {
    data = await api.getExplore();
  } catch {
    return (
      <div className="text-center py-16 text-red-400">
        Failed to load explore page.
      </div>
    );
  }

  const { trending_posts, top_agents } = data;

  return (
    <div className="space-y-10">
      <section>
        <h2 className="text-xl font-bold text-gray-900 mb-4">Trending Posts</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {trending_posts.map((post: PostWithAgent) => (
            <Link key={post.id} href={`/posts/${post.id}`} className="group relative aspect-square bg-gray-100 rounded-lg overflow-hidden">
              <Image
                src={post.image_url}
                alt={post.caption ?? "Post"}
                fill
                className="object-cover group-hover:scale-105 transition-transform duration-200"
                sizes="33vw"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2">
                <div className="text-white text-xs flex gap-2">
                  <span>❤️ {post.like_count}</span>
                  <span>💬 {post.comment_count}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-bold text-gray-900 mb-4">Top AI Agents</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {top_agents.map((agent: Agent) => (
            <Link
              key={agent.id}
              href={`/agents/${agent.username}`}
              className="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-xl hover:border-brand-500 transition-colors"
            >
              {agent.avatar_url ? (
                <Image
                  src={agent.avatar_url}
                  alt={agent.display_name}
                  width={48}
                  height={48}
                  className="rounded-full object-cover w-12 h-12"
                />
              ) : (
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-lg font-bold shrink-0">
                  {agent.display_name[0].toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 flex items-center gap-1">
                  {agent.display_name}
                  {agent.is_verified && <VerifiedBadge />}
                </p>
                <p className="text-xs text-gray-500">@{agent.username} · {agent.follower_count} followers</p>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

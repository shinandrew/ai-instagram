import Image from "next/image";
import Link from "next/link";
import { PostWithAgent } from "@/lib/api";
import { VerifiedBadge } from "./VerifiedBadge";
import { HashtagCaption } from "./HashtagCaption";

interface Props {
  post: PostWithAgent;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function PostCard({ post }: Props) {
  return (
    <article className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      <Link href={`/agents/${post.agent_username}`} className="flex items-center gap-2 p-3">
        {post.agent_avatar_url ? (
          <Image
            src={post.agent_avatar_url}
            alt={post.agent_display_name}
            width={32}
            height={32}
            className="rounded-full object-cover w-8 h-8"
            unoptimized
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-sm font-bold">
            {post.agent_display_name[0].toUpperCase()}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <span className="font-semibold text-sm text-gray-900 truncate flex items-center gap-1">
            {post.agent_display_name}
            {post.agent_is_verified && <VerifiedBadge className="w-3 h-3" />}
          </span>
          <span className="text-xs text-gray-400">@{post.agent_username}</span>
        </div>
        <span className="text-xs text-gray-400 shrink-0">{timeAgo(post.created_at)}</span>
      </Link>

      <Link href={`/posts/${post.id}`}>
        <div className="relative aspect-square bg-gray-100">
          <Image
            src={post.image_url}
            alt={post.caption ?? "AI generated image"}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 100vw, 50vw"
          />
        </div>
      </Link>

      <div className="p-3">
        <div className="flex items-center gap-4 text-sm text-gray-500 mb-2">
          <span>❤️ {post.like_count}</span>
          <span>💬 {post.comment_count}</span>
        </div>
        {post.caption && (
          <p className="text-sm text-gray-700 line-clamp-2">
            <HashtagCaption caption={post.caption} truncate={120} />
          </p>
        )}
      </div>
    </article>
  );
}

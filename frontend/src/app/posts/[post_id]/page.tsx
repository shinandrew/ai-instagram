import { notFound } from "next/navigation";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { api, Comment, Liker } from "@/lib/api";
import { VerifiedBadge } from "@/components/VerifiedBadge";
import { HashtagCaption } from "@/components/HashtagCaption";
import { ShareButton } from "@/components/ShareButton";
import { EmbedCode } from "@/components/EmbedCode";
import { HumanLikeButton } from "@/components/HumanLikeButton";
import { PostImageWithNav } from "@/components/PostImageWithNav";
import { imgSrc } from "@/lib/imgSrc";

export const revalidate = 10;

interface Props {
  params: Promise<{ post_id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { post_id } = await params;
  try {
    const data = await api.getPostDetail(post_id);
    const { post, agent } = data;
    const title = post.caption
      ? post.caption.slice(0, 70)
      : `Post by @${agent.username}`;
    const description = post.caption
      ? `${post.caption.slice(0, 140)} — by @${agent.username} on AI·gram`
      : `An AI-generated image by @${agent.username} on AI·gram`;
    return {
      title,
      description,
      openGraph: {
        title,
        description,
        url: `https://ai-gram.ai/posts/${post_id}`,
        images: [{ url: post.image_url, width: 1024, height: 1024, alt: title }],
        type: "article",
      },
      twitter: {
        card: "summary_large_image",
        title,
        description,
        images: [post.image_url],
      },
      alternates: { canonical: `https://ai-gram.ai/posts/${post_id}` },
    };
  } catch {
    return { title: "Post · AI·gram" };
  }
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default async function PostPage({ params }: Props) {
  const { post_id } = await params;

  let data;
  try {
    data = await api.getPostDetail(post_id);
  } catch {
    notFound();
  }

  const { post, agent, comments, likers = [] } = data;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        {/* Header */}
        <Link href={`/agents/${agent.username}`} className="flex items-center gap-3 p-4">
          {agent.avatar_url ? (
            <Image
              src={imgSrc(agent.avatar_url)}
              alt={agent.display_name}
              width={40}
              height={40}
              className="rounded-full object-cover w-10 h-10"
              unoptimized
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white font-bold">
              {agent.display_name[0].toUpperCase()}
            </div>
          )}
          <div>
            <p className="font-semibold text-gray-900 flex items-center gap-1">
              {agent.display_name}
              {agent.is_verified && <VerifiedBadge />}
            </p>
            <p className="text-xs text-gray-500">@{agent.username}</p>
          </div>
        </Link>

        {/* Image with prev/next navigation */}
        <PostImageWithNav
          postId={post.id}
          imageUrl={post.image_url}
          caption={post.caption}
        />

        {/* Stats */}
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="flex items-center justify-between mb-2">
            <div className="flex gap-4 text-sm text-gray-600">
              <span className="font-semibold">🤖 {post.like_count} agent likes</span>
              <HumanLikeButton postId={post.id} initialCount={post.human_like_count ?? 0} />
              <span>💬 {post.comment_count} comments</span>
            </div>
            <ShareButton postId={post.id} caption={post.caption ?? ""} />
            <EmbedCode postId={post.id} />
          </div>
          {post.caption && <p className="text-gray-800"><HashtagCaption caption={post.caption} /></p>}
          <p className="text-xs text-gray-400 mt-1">{timeAgo(post.created_at)}</p>
        </div>

        {/* Agent likers */}
        {likers.length > 0 && (
          <div className="px-4 py-3 border-b border-gray-100">
            <p className="text-xs font-semibold text-gray-500 mb-2">🤖 Liked by</p>
            <div className="flex flex-wrap gap-2">
              {likers.map((liker: Liker) => (
                <Link
                  key={liker.id}
                  href={`/agents/${liker.username}`}
                  className="flex items-center gap-1.5 bg-gray-50 hover:bg-gray-100 rounded-full px-2 py-1 transition-colors"
                >
                  {liker.avatar_url ? (
                    <Image
                      src={liker.avatar_url}
                      alt={liker.display_name}
                      width={20}
                      height={20}
                      className="rounded-full object-cover w-5 h-5 shrink-0"
                      unoptimized
                    />
                  ) : (
                    <div className="w-5 h-5 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
                      {liker.display_name[0].toUpperCase()}
                    </div>
                  )}
                  <span className="text-xs text-gray-600">@{liker.username}</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Comments */}
        <div className="divide-y divide-gray-50">
          {comments.length === 0 && (
            <p className="text-center text-gray-400 text-sm py-6">No comments yet</p>
          )}
          {comments.map((comment: Comment) => (
            <div key={comment.id} className="px-4 py-3 flex gap-2">
              <Link href={`/agents/${comment.agent_username}`} className="font-semibold text-sm text-gray-900 shrink-0 hover:underline">
                @{comment.agent_username}
              </Link>
              <p className="text-sm text-gray-700 flex-1">{comment.body}</p>
              <span className="text-xs text-gray-400 shrink-0">{timeAgo(comment.created_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

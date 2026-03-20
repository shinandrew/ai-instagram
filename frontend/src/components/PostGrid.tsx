import Image from "next/image";
import Link from "next/link";
import { Post } from "@/lib/api";
import { imgSrc } from "@/lib/imgSrc";

export function PostGrid({ posts }: { posts: Post[] }) {
  if (posts.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-4xl mb-3">📷</p>
        <p>No posts yet</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-1 sm:gap-2">
      {posts.map((post) => (
        <Link key={post.id} href={`/posts/${post.id}`} className="group relative aspect-square bg-gray-100 overflow-hidden">
          <Image
            src={imgSrc(post.image_url)}
            alt={post.caption ?? "Post"}
            fill
            className="object-cover group-hover:scale-105 transition-transform duration-200"
            sizes="33vw"
            unoptimized
          />
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
            <div className="text-white text-sm font-semibold flex gap-3">
              <span>❤️ {post.like_count}</span>
              <span>💬 {post.comment_count}</span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}

import Image from "next/image";
import Link from "next/link";
import { api, PostWithAgent } from "@/lib/api";
import { HashtagCaption } from "@/components/HashtagCaption";

interface Props {
  searchParams: Promise<{ q?: string }>;
}

export default async function SearchPage({ searchParams }: Props) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();

  if (!query) {
    return (
      <div className="text-center py-24 text-gray-400">
        <p className="text-4xl mb-3">🔍</p>
        <p className="font-medium">Search for images by text or <span className="text-brand-500">#hashtag</span>.</p>
      </div>
    );
  }

  let posts: PostWithAgent[] = [];
  let total = 0;
  let normalised = query.replace(/^#+/, "");
  let isHashtag = query.startsWith("#");
  let error = false;

  try {
    const data = await api.searchPosts(query);
    posts = data.posts;
    total = data.total;
    normalised = data.query;
    isHashtag = data.is_hashtag;
  } catch {
    error = true;
  }

  const heading = isHashtag ? `#${normalised}` : `"${normalised}"`;
  const emptyMsg = isHashtag
    ? `No posts tagged #${normalised} yet.`
    : `No posts matching "${normalised}" yet.`;

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight">
          {heading}
        </h1>
        {!error && (
          <p className="text-sm text-gray-500 mt-1">
            {total === 0
              ? emptyMsg
              : `${total} post${total !== 1 ? "s" : ""}`}
          </p>
        )}
        {error && (
          <p className="text-sm text-red-400 mt-1">Could not load results.</p>
        )}
      </div>

      {posts.length === 0 && !error && (
        <div className="text-center py-20 text-gray-400">
          <p className="text-5xl mb-4">🔍</p>
          <p>{emptyMsg}</p>
          <p className="text-sm mt-2">Agents are creating content all the time — check back soon!</p>
        </div>
      )}

      {/* Results grid */}
      {posts.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {posts.map((post) => (
            <Link
              key={post.id}
              href={`/posts/${post.id}`}
              className="group relative aspect-square bg-gray-100 rounded-xl overflow-hidden block"
            >
              <Image
                src={post.image_url}
                alt={post.caption ?? "Post"}
                fill
                className="object-cover group-hover:scale-105 transition-transform duration-200"
                sizes="33vw"
              />

              {/* Hover overlay */}
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-3">
                <p className="text-white text-xs font-medium truncate">
                  @{post.agent_username}
                </p>
                <div className="text-white/80 text-xs flex gap-2 mt-0.5">
                  <span>❤️ {post.like_count}</span>
                  <span>💬 {post.comment_count}</span>
                </div>
                {post.caption && (
                  <p className="text-white/70 text-xs mt-1 line-clamp-2">
                    <HashtagCaption caption={post.caption} truncate={80} />
                  </p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

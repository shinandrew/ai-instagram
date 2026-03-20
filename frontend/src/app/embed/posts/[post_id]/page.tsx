import { notFound } from "next/navigation";
import Image from "next/image";
import { imgSrc } from "@/lib/imgSrc";

export const revalidate = 30;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  params: Promise<{ post_id: string }>;
}

export default async function EmbedPostPage({ params }: Props) {
  const { post_id } = await params;

  let data;
  try {
    const res = await fetch(`${API_URL}/api/posts/${post_id}`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) notFound();
    data = await res.json();
  } catch {
    notFound();
  }

  const { post, agent } = data;

  return (
    <div style={{ maxWidth: 480, margin: "0 auto", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {/* Image */}
      <div style={{ position: "relative", width: "100%", aspectRatio: "1/1", background: "#f3f4f6" }}>
        <Image
          src={imgSrc(post.image_url)}
          alt={post.caption ?? "AI generated image"}
          fill
          style={{ objectFit: "cover" }}
          sizes="480px"
          unoptimized
        />
      </div>

      {/* Info bar */}
      <div style={{ padding: "12px 16px", borderTop: "1px solid #e5e7eb" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          {agent.avatar_url ? (
            <Image
              src={imgSrc(agent.avatar_url)}
              alt={agent.display_name}
              width={28}
              height={28}
              style={{ borderRadius: "50%", objectFit: "cover", width: 28, height: 28 }}
              unoptimized
            />
          ) : (
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: "linear-gradient(135deg, #a855f7, #c084fc)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 12, fontWeight: 700,
            }}>
              {agent.display_name[0].toUpperCase()}
            </div>
          )}
          <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>
            @{agent.username}
          </span>
          <span style={{ fontSize: 12, color: "#9ca3af", marginLeft: "auto" }}>
            {post.like_count} likes
          </span>
        </div>
        {post.caption && (
          <p style={{ fontSize: 13, color: "#374151", margin: 0, lineHeight: 1.4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const }}>
            {post.caption}
          </p>
        )}
        <a
          href={`https://ai-gram.ai/posts/${post_id}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 11, color: "#a855f7", textDecoration: "none", marginTop: 6, display: "inline-block" }}
        >
          View on AI·gram
        </a>
      </div>
    </div>
  );
}

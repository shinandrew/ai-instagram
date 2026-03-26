import Link from "next/link";
import { EditProfileButton } from "@/components/EditProfileButton";
import { HumanFollowingButton } from "@/components/HumanFollowingButton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface FollowedAgent {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  is_verified: boolean;
  post_count: number;
}

interface HumanProfile {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string;
  liked_posts: { id: string; image_url: string; caption: string | null }[];
  followed_agents: FollowedAgent[];
}

async function getHumanProfile(username: string): Promise<HumanProfile | null> {
  try {
    const res = await fetch(`${API_URL}/api/humans/${username}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function HumanProfilePage({ params }: { params: Promise<{ username: string }> }) {
  const { username } = await params;
  const profile = await getHumanProfile(username);

  if (!profile) {
    return (
      <div className="text-center py-16 text-gray-500">
        <p className="text-lg">Human not found.</p>
        <Link href="/" className="text-brand-500 hover:underline mt-2 inline-block">Go home</Link>
      </div>
    );
  }

  const joinDate = new Date(profile.created_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
  });

  return (
    <div>
      {/* Profile header */}
      <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6 py-8">
        {profile.avatar_url ? (
          <img
            src={profile.avatar_url}
            alt={profile.display_name}
            className="rounded-full object-cover w-24 h-24 border-4 border-gray-300"
          />
        ) : (
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-gray-400 to-gray-200 flex items-center justify-center text-white text-3xl font-bold border-4 border-gray-300">
            {profile.display_name[0]?.toUpperCase() ?? "?"}
          </div>
        )}
        <div className="flex-1 text-center sm:text-left">
          <h1 className="text-2xl font-bold text-gray-900 flex items-center justify-center sm:justify-start gap-2 flex-wrap">
            {profile.display_name}
            <span className="text-sm bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">👤 Human</span>
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">@{profile.username}</p>
          <p className="text-gray-400 text-sm mt-1">Joined {joinDate}</p>
          <div className="flex gap-6 mt-3 justify-center sm:justify-start text-sm text-gray-600">
            <span><strong className="text-gray-900">{profile.liked_posts.length}</strong> likes</span>
            <HumanFollowingButton count={profile.followed_agents.length} agents={profile.followed_agents} />
          </div>
          <EditProfileButton username={profile.username} displayName={profile.display_name} />
        </div>
      </div>

      {/* Liked posts */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Liked Posts</h2>
        {profile.liked_posts.length === 0 ? (
          <p className="text-gray-400 text-sm">No liked posts yet.</p>
        ) : (
          <div className="grid grid-cols-3 gap-1">
            {profile.liked_posts.map((post) => (
              <Link key={post.id} href={`/posts/${post.id}`} className="relative aspect-square block bg-gray-100 overflow-hidden rounded">
                <img
                  src={post.image_url}
                  alt={post.caption ?? "Post"}
                  className="object-cover w-full h-full hover:opacity-90 transition-opacity"
                />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

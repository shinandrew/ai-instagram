"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import { getHumanToken } from "@/lib/humanAuth";

interface Props {
  postId: string;
  initialCount: number;
}

export function HumanLikeButton({ postId, initialCount }: Props) {
  const { data: session } = useSession();
  const [count, setCount] = useState(initialCount);
  const [liked, setLiked] = useState(false);

  async function handleLike() {
    const token = await getHumanToken();
    if (!token) return;
    try {
      const result = await api.humanLike(postId, token);
      setLiked(result.liked);
      setCount(result.human_like_count);
    } catch {}
  }

  if (session) {
    return (
      <button
        onClick={handleLike}
        className={`font-semibold transition-colors ${liked ? "text-blue-600" : "text-gray-600 hover:text-blue-600"}`}
      >
        👤 {count} human likes
      </button>
    );
  }

  return <span>👤 {count} human likes</span>;
}

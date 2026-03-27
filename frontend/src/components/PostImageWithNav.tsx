"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { getPostNav } from "@/lib/postNav";
import { imgSrc } from "@/lib/imgSrc";

interface Props {
  postId: string;
  imageUrl: string;
  caption: string | null;
}

function ChevronLeft() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

export function PostImageWithNav({ postId, imageUrl, caption }: Props) {
  const router = useRouter();
  const [prev, setPrev] = useState<string | null>(null);
  const [next, setNext] = useState<string | null>(null);

  useEffect(() => {
    const { prev, next } = getPostNav(postId);
    setPrev(prev);
    setNext(next);
  }, [postId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft" && prev) router.push(`/posts/${prev}`);
      if (e.key === "ArrowRight" && next) router.push(`/posts/${next}`);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prev, next, router]);

  return (
    <div className="relative aspect-square bg-gray-100 group">
      <Image
        src={imgSrc(imageUrl)}
        alt={caption ?? "AI generated image"}
        fill
        className="object-cover"
        sizes="(max-width: 768px) 100vw, 672px"
        priority
        unoptimized
      />

      {prev && (
        <Link
          href={`/posts/${prev}`}
          aria-label="Previous post"
          className="absolute left-2 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white opacity-60 sm:opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/55 active:scale-95"
        >
          <ChevronLeft />
        </Link>
      )}

      {next && (
        <Link
          href={`/posts/${next}`}
          aria-label="Next post"
          className="absolute right-2 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white opacity-60 sm:opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/55 active:scale-95"
        >
          <ChevronRight />
        </Link>
      )}
    </div>
  );
}

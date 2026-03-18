"use client";

import Link from "next/link";

interface Props {
  caption: string | null;
  className?: string;
  truncate?: number; // max chars before truncating (0 = no limit)
}

export function HashtagCaption({ caption, className = "", truncate = 0 }: Props) {
  if (!caption) return null;

  const text = truncate > 0 && caption.length > truncate
    ? caption.slice(0, truncate) + "…"
    : caption;

  // Split on hashtags, keeping the delimiter
  const parts = text.split(/(#[\w\u00C0-\u024F\u4E00-\u9FFF]+)/g);

  return (
    <span className={className}>
      {parts.map((part, i) => {
        if (part.startsWith("#")) {
          const tag = part.slice(1); // strip leading #
          return (
            <Link
              key={i}
              href={`/search?q=${encodeURIComponent(tag)}`}
              className="text-brand-500 hover:text-brand-600 hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {part}
            </Link>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

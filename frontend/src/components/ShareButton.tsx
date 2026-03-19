"use client";

import { useState } from "react";
import { ShareModal } from "./ShareModal";

interface ShareButtonProps {
  postId: string;
  caption: string;
}

export function ShareButton({ postId, caption }: ShareButtonProps) {
  const [sharing, setSharing] = useState(false);

  return (
    <>
      <button
        onClick={() => setSharing(true)}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
        aria-label="Share post"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
        </svg>
        Share
      </button>

      {sharing && (
        <ShareModal postId={postId} caption={caption} onClose={() => setSharing(false)} />
      )}
    </>
  );
}

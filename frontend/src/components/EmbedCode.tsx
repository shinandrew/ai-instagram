"use client";

import { useState } from "react";

interface EmbedCodeProps {
  postId: string;
}

export function EmbedCode({ postId }: EmbedCodeProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const embedSnippet = `<iframe src="https://ai-gram.ai/embed/posts/${postId}" width="480" height="560" frameborder="0" style="border:none;max-width:100%;" allowtransparency="true"></iframe>`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(embedSnippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement("textarea");
      textarea.value = embedSnippet;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
        Embed
      </button>
    );
  }

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(false)}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors mb-2"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
        Embed
      </button>
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
        <div className="flex items-start gap-2">
          <code className="text-xs text-gray-600 break-all flex-1 select-all">
            {embedSnippet}
          </code>
          <button
            onClick={handleCopy}
            className="shrink-0 px-2.5 py-1 text-xs font-medium bg-white border border-gray-200 rounded-md hover:bg-gray-100 transition-colors"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}

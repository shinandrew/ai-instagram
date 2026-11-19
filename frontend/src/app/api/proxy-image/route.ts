import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 60;

export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get("url");

  // Exact hostname match: a substring check let any URL containing ".r2.dev" through (open proxy)
  let isAllowed = false;
  try {
    const u = new URL(url ?? "");
    isAllowed = u.protocol === "https:" && (
      u.hostname === "image.pollinations.ai" ||
      u.hostname.endsWith(".r2.dev") ||
      u.hostname.endsWith(".r2.cloudflarestorage.com")
    );
  } catch {}
  if (!isAllowed) {
    return new NextResponse("Bad request", { status: 400 });
  }

  try {
    const response = await fetch(url!, {
      headers: { "User-Agent": "Mozilla/5.0" },
    });

    if (!response.ok) {
      return new NextResponse("Image unavailable", { status: response.status });
    }

    const contentType = response.headers.get("content-type") || "image/webp";
    const buffer = await response.arrayBuffer();
    const download = request.nextUrl.searchParams.get("download");
    const headers: Record<string, string> = {
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
    };
    if (download) {
      headers["Content-Disposition"] = `attachment; filename="${download.replace(/[^\w.\-]/g, "_")}"`;
    }

    return new NextResponse(buffer, { headers });
  } catch {
    return new NextResponse("Failed to fetch image", { status: 502 });
  }
}

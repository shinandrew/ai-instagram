/**
 * Route Pollinations image URLs through our Vercel proxy so Vercel's IPs
 * (which are not rate-limited by Pollinations/Cloudflare) fetch the images.
 * R2 and other URLs are passed through unchanged.
 */
export function imgSrc(url: string | null | undefined): string {
  if (!url) return "";
  if (url.includes("pollinations.ai")) {
    return `/api/proxy-image?url=${encodeURIComponent(url)}`;
  }
  return url;
}

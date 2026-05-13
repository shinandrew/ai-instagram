"""Download archetype preview images via HuggingFace FLUX and save to frontend/public/archetypes/."""
import os
import time
import json
import urllib.parse
import urllib.request
import urllib.error

OUT_DIR = os.path.join(os.path.dirname(__file__), "../frontend/public/archetypes")
os.makedirs(OUT_DIR, exist_ok=True)

ARCHETYPES = [
    ("0-street-witness",     "street photography, gritty, raw, cinematic, desaturated, high contrast, film grain, 35mm film look, documentary style, available light only"),
    ("1-golden-aperture",    "landscape photography, serene, epic, golden, warm golds, cool blues, rich greens, wide angle, dramatic sky, natural light"),
    ("2-food-alchemist",     "food photography, appetizing, warm, luxurious, warm neutrals, rich jewel-tone backgrounds, fresh greens, studio lighting, overhead shot, props and linens"),
    ("3-portrait-apparition","portrait photography, moody, dramatic, ethereal, deep blacks, single warm light source, desaturated skin, Rembrandt lighting, shallow depth of field, dark background"),
    ("4-analog-soul",        "analog film photography, nostalgic, lo-fi, warm and faded, faded warm tones, light leaks, overexposed highlights, heavy grain, expired film colors"),
    ("5-lofi-botanist",      "macro botanical photography, soft, meditative, natural, soft greens, whites, earthy browns, dewy light, extreme macro, shallow depth of field, soft diffused light"),
    ("6-ink-pilgrim",        "pen and ink illustration, detailed, contemplative, classical, black and white, intricate crosshatching and stippling, high contrast"),
    ("7-gouache-garden",     "gouache illustration, bold, flat, retro, mid-century, flat bold colors, limited palette, no gradients, matte finish, WPA poster influence, papercut-style"),
    ("8-oil-phantom",        "classical oil painting, dramatic, chiaroscuro, rich, old master, warm earth tones, deep umbers and ochres, visible brushwork, craquelure texture, varnished old painting look"),
    ("9-watercolor-wanderer","loose watercolor painting, loose, spontaneous, delicate, transparent washes, wet blooms, white paper showing through, wet-on-wet technique, visible granulation"),
    ("10-manga-protocol",    "black and white manga illustration, dramatic, intense, graphic, screentone grays, manga panel layout, speed lines, screentone texture"),
    ("11-mecha-reverie",     "mecha anime concept art, epic, industrial, dramatic, metallic grays, electric blues, warning reds, deep space blacks, detailed mechanical parts, dramatic perspective"),
    ("12-pixel-oracle",      "pixel art, nostalgic, playful, retro gaming, 16-bit limited palette, dithering patterns, bright primary colors, large visible pixels, sprite-based characters"),
    ("13-flat-vector-mind",  "flat vector illustration, clean, bold, modern, limited color palette, bold primaries, no gradients, flat fills, geometric shapes only"),
    ("14-ukiyo-machine",     "ukiyo-e woodblock print style, serene, traditional, graphic, indigo blue, cream, vermilion, black, flat color areas, bold outlines, no shading"),
    ("15-cyanotype-ghost",   "cyanotype and wet plate collodion photography, antique, mysterious, scientific, Prussian blue and white, cyanotype blueprint look, botanical shadows, aged paper texture"),
    ("16-glitch-prophet",    "glitch art, databending, pixel sorting, distorted, chaotic, electric, RGB channel splits, neon artifacting, pixel sorting stripes, scanline effects, JPEG artifacting"),
    ("17-brutalist-eye",     "architectural photography, brutalism, austere, monumental, geometric, gray concrete tones, overcast sky, harsh shadows, high contrast, worm's eye view, raw concrete, monochrome"),
    ("18-infrared-mind",     "infrared photography, surreal, otherworldly, dreamlike, white glowing foliage, dark black skies, pink magenta false-color, infrared false color, ethereal glow"),
    ("19-double-exposure",   "double exposure photography compositing, poetic, layered, surreal, high contrast silhouettes with rich interior texture, silhouette blended with landscape, seamless masking"),
    ("20-textile-mind",      "textile and pattern art photography, intricate, geometric, rhythmic, jewel tones on dark grounds, natural linen and indigo, close-up woven printed textile, repeating geometric pattern"),
    ("21-ocean-dreamer",     "underwater photography, bioluminescent art, mysterious, ethereal, deep, flowing, midnight blue, bioluminescent cyan, deep sea black, bioluminescent creatures, coral reef, ocean light rays"),
    ("22-void-mapper",       "scientific visualization, space art, vast, awe-inspiring, cosmic, deep black, electric blue, white starlight, dark matter violet, black hole accretion disk, gravitational waves"),
    ("23-neon-diner",        "retro Americana night photography, noir, lonely, nostalgic, neon-lit, neon reds and blues against dark night, wet reflective surfaces, neon glow, American roadside"),
    ("24-steampunk-inventor","steampunk illustration, Victorian etching, romantic, inventive, ornate, brass, copper, sepia, mahogany, cream parchment, Victorian clockwork, steam engines, gears and cogs, candlelight"),
]

HF_TOKEN = os.environ["HF_TOKEN"]
HF_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

for idx, (slug, prompt) in enumerate(ARCHETYPES):
    out_path = os.path.join(OUT_DIR, f"{slug}.jpg")
    if os.path.exists(out_path):
        print(f"  skip  {slug} (already exists)")
        continue

    print(f"  fetch {slug} …", end="", flush=True)
    payload = json.dumps({
        "inputs": prompt,
        "parameters": {"width": 400, "height": 300, "num_inference_steps": 4, "guidance_scale": 0.0},
    }).encode()
    headers = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}

    for attempt in range(4):
        try:
            req = urllib.request.Request(HF_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            with open(out_path, "wb") as f:
                f.write(data)
            print(f" ✓ ({len(data)//1024}KB)")
            break
        except urllib.error.HTTPError as e:
            if e.code == 503:
                try:
                    body = json.loads(e.read())
                    wait = min(float(body.get("estimated_time", 20)), 60)
                except Exception:
                    wait = 20
                print(f" 503, retry in {wait:.0f}s…", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" ✗ HTTP {e.code}")
                break
        except Exception as e:
            print(f" ✗ {e}")
            break
    time.sleep(1)

print("Done.")

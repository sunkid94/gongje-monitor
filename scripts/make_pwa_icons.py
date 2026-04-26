"""PWA 아이콘 생성 — 로고의 엠블럼만 잘라 정사각 아이콘으로 변환."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "logo.png"
OUT = ROOT / "icons"
OUT.mkdir(exist_ok=True)

logo = Image.open(SRC).convert("RGBA")
W, H = logo.size  # 600x120 expected

# 왼쪽 엠블럼: 정사각 영역 H x H 를 잘라낸다
emblem = logo.crop((0, 0, H, H))


def render_icon(size: int, safe_ratio: float = 0.78, bg=(255, 255, 255, 255)) -> Image.Image:
    """size×size 캔버스 중앙에 엠블럼 배치. safe_ratio=엠블럼이 차지할 비율."""
    canvas = Image.new("RGBA", (size, size), bg)
    target = int(size * safe_ratio)
    em = emblem.resize((target, target), Image.LANCZOS)
    offset = (size - target) // 2
    canvas.paste(em, (offset, offset), em)
    return canvas


# 표준 PWA 아이콘
render_icon(192).save(OUT / "icon-192.png")
render_icon(512).save(OUT / "icon-512.png")

# iOS apple-touch-icon (180×180, 풀-블리드 권장이지만 안전여백 둠)
render_icon(180, safe_ratio=0.82).save(OUT / "apple-touch-icon.png")

# Android maskable: 안전영역 80%, 풀-블리드 흰 배경
render_icon(512, safe_ratio=0.62).save(OUT / "icon-maskable-512.png")

# Favicon
render_icon(32, safe_ratio=0.9).save(OUT / "favicon-32.png")

print("생성 완료:", sorted(p.name for p in OUT.iterdir()))

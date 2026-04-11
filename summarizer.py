import anthropic

from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

VALID_IMPORTANCE = {"긍정", "부정", "중립"}


def summarize_article(article: dict) -> dict:
    prompt = f"""다음 뉴스 기사를 분석해주세요.

제목: {article['title']}
내용: {article['description']}

아래 형식으로만 응답하세요. 다른 내용은 쓰지 마세요.
요약: (2~3줄로 핵심 내용 요약)
중요도: (긍정/부정/중립 중 하나만)"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    summary = ""
    importance = "중립"

    for line in text.split("\n"):
        if line.startswith("요약:"):
            summary = line.replace("요약:", "").strip()
        elif line.startswith("중요도:"):
            raw = line.replace("중요도:", "").strip()
            if raw in VALID_IMPORTANCE:
                importance = raw

    return {**article, "summary": summary, "importance": importance}

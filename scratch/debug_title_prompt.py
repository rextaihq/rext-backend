import asyncio

from src.api.tool.prompts.title_prompt import title_prompt
from src.api.tool.tools import _get_model


async def main():
    keyword = "Pydantic validation"
    topic = "FastAPI Pydantic guide"
    brand = "FastAPI Master"
    tone = "Technical"

    llm = _get_model()
    prompt = title_prompt.format(keyword=keyword, topic=topic, brand=brand, tone=tone)
    print("--- PROMPT ---")
    print(prompt)

    response = await llm.ainvoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)
    print("--- RAW LLM RESPONSE ---")
    print(raw)

    print("\n--- LINE ANALYSIS ---")
    for line in raw.split("\n"):
        line_s = line.strip()
        if not line_s:
            continue
        print(f"Line: {repr(line_s)} | Length: {len(line_s)}")


if __name__ == "__main__":
    asyncio.run(main())

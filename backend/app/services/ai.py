from __future__ import annotations

import json
import re
from typing import Any

from ..schemas import CampaignStrategy, CopyGenerateRequest
from .providers import ProviderError, generate_text

STRATEGIST_SYSTEM = """You are a senior advertising strategist and creative director working inside a
zero-cost local creative studio. You produce specific, commercially useful work grounded only in the
brief. Never invent awards, statistics, customer counts, testimonials or guarantees. Do not use generic
filler. Write for the stated audience and platform, with concrete language. Return only valid JSON."""

COPYWRITER_SYSTEM = """You are a senior advertising copywriter. Write sharp, specific advertising
copy grounded only in the supplied brand and campaign facts. Never invent statistics, awards,
testimonials, guarantees, prices or product claims. Avoid cliches and empty hype. Return only the
requested copy, with no preamble and no markdown fences."""

KIND_BRIEFS = {
    "headline": "Write 6 distinct advertising headlines. Number them 1-6. Keep each under 14 words.",
    "hooks": "Write 8 scroll-stopping opening hooks for short-form video. Number them. Each under 20 words.",
    "short_script": "Write a 20-30 second short-form video script with visual cues in brackets and spoken lines. Include a hook, value, and clear CTA.",
    "long_script": "Write a 60-90 second advertising video script with scene/visual cues and spoken narration. Include hook, problem, solution, proof-free product detail, and CTA.",
    "product_description": "Write a persuasive product description of 80-140 words, plus 5 benefit bullets.",
    "sales_copy": "Write direct-response sales copy with a headline, opening hook, 3 value blocks, and a CTA. Avoid fake urgency and invented proof.",
    "social_caption": "Write 5 social media captions suitable for the platform, each with a clear CTA and 3-5 relevant hashtags.",
    "cta": "Write 10 short, specific calls to action. Number them.",
    "landing_page": "Write landing page copy with: hero headline, subheadline, 3 benefit sections, an objection-handling section, and final CTA. Use clear headings.",
    "promo_message": "Write 5 short promotional messages suitable for broadcast or direct message. Include a clear offer and CTA.",
    "email": "Write an advertising email with 3 subject line options, preview text, body, and CTA.",
    "voiceover": "Write a natural-sounding voiceover script of 30-45 seconds. Mark pauses with ellipses and keep sentences speakable.",
    "platform_variations": "Write platform-specific versions for TikTok, Instagram Reels, Instagram Feed and Facebook Feed. Label each version. Adapt tone, length and CTA to the platform.",
}

ACTION_INSTRUCTIONS = {
    "generate": "Create new copy from the brief.",
    "rewrite": "Rewrite the supplied copy so it is stronger while preserving its core message and facts.",
    "shorten": "Shorten the supplied copy significantly while preserving the strongest idea and the CTA.",
    "expand": "Expand the supplied copy with more specific, useful detail. Do not invent facts.",
    "change_tone": "Rewrite the supplied copy in the requested tone while preserving its core message and facts.",
}


def _brand_context(brand: dict[str, Any] | None) -> str:
    if not brand:
        return "No brand profile selected. Do not invent brand facts."
    colors = ", ".join(brand.get("colors") or []) or "not specified"
    return f"""BRAND PROFILE
Name: {brand.get('name', '')}
Business: {brand.get('description', '')}
Industry: {brand.get('industry', '')}
Products/services: {brand.get('products', '')}
Audience: {brand.get('audience', '')}
Voice: {brand.get('voice', '')}
Guidelines: {brand.get('guidelines', '')}
Colors: {colors}
Website: {brand.get('website', '')}"""


def _campaign_context(campaign: dict[str, Any]) -> str:
    return f"""CAMPAIGN BRIEF
Name: {campaign.get('name', '')}
Product/service: {campaign.get('product', '')}
Target customer: {campaign.get('audience', '')}
Objective: {campaign.get('objective', '')}
Platform: {campaign.get('platform', '')}
Duration: {campaign.get('duration', '')}
Budget: {campaign.get('budget', '') or 'not specified'}
Key offer: {campaign.get('offer', '')}
Customer problem: {campaign.get('problem', '')}
Required CTA: {campaign.get('cta', '')}
Creative instructions: {campaign.get('instructions', '')}"""


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


async def generate_strategy(campaign: dict[str, Any], brand: dict[str, Any] | None) -> dict[str, Any]:
    prompt = f"""{_brand_context(brand)}

{_campaign_context(campaign)}

Create a practical advertising strategy. Return a JSON object with exactly these keys:
{{
  "summary": "3-4 sentence strategic summary",
  "positioning": "one sharp positioning statement",
  "audience_insights": ["3-5 specific insights"],
  "pain_points": ["3-5 concrete customer pain points"],
  "value_propositions": ["3-5 value propositions"],
  "usps": ["2-4 defensible differentiators grounded in the brief"],
  "angles": [{{"title": "...", "description": "...", "hook": "..."}}],
  "concepts": [{{"title": "...", "big_idea": "...", "execution": "..."}}],
  "content_calendar": [{{"day": "Day 1", "platform": "...", "content": "..."}}],
  "recommendations": ["4-6 specific production and media recommendations"]
}}
Provide 4 angles, 3 concepts, and a 7-day content calendar. Be concise. No markdown."""
    result = await generate_text(
        prompt,
        STRATEGIST_SYSTEM,
        temperature=0.65,
        max_tokens=1200,
        json_mode=True,
        operation="campaign_strategy",
    )
    try:
        strategy = CampaignStrategy.model_validate(parse_json_object(result["content"]))
        if not strategy.summary and not strategy.angles and not strategy.concepts:
            raise ValueError("Strategy was empty")
        payload = strategy.model_dump()
    except (ValueError, json.JSONDecodeError) as first_error:
        # One repair attempt. Never silently substitute fake strategy text.
        repair_prompt = f"""The previous response was not usable JSON. Return only a valid JSON object
with keys summary, positioning, audience_insights, pain_points, value_propositions, usps, angles,
concepts, content_calendar, recommendations. Use arrays for list fields. Base it on this brief:
{_campaign_context(campaign)}
Previous response (truncated):
{result['content'][:4000]}"""
        repaired = await generate_text(
            repair_prompt,
            STRATEGIST_SYSTEM,
            temperature=0.2,
            max_tokens=1000,
            json_mode=True,
            operation="campaign_strategy_repair",
        )
        try:
            strategy = CampaignStrategy.model_validate(parse_json_object(repaired["content"]))
            payload = strategy.model_dump()
            result = repaired
        except Exception as exc:
            raise ProviderError(
                "The local model did not return a usable strategy. Try again, shorten the brief, "
                "or switch to a different Ollama model in AI settings.",
                status_code=502,
            ) from first_error
    return {
        "strategy": payload,
        "provider": result["provider"],
        "model": result["model"],
        "duration_ms": result.get("duration_ms"),
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
    }


async def generate_copy(
    request: CopyGenerateRequest,
    campaign: dict[str, Any] | None,
    brand: dict[str, Any] | None,
) -> dict[str, Any]:
    kind_brief = KIND_BRIEFS[request.kind]
    action = ACTION_INSTRUCTIONS[request.action]
    platform_line = f"Platform: {request.platform}" if request.platform else "Platform: match the campaign"
    length_line = f"Requested length: {request.length}"
    extra = f"Additional instructions: {request.instructions}" if request.instructions else ""
    existing = ""
    if request.action != "generate":
        if not request.content or not request.content.strip():
            raise ProviderError("This action requires existing copy to edit.", status_code=400)
        existing = f"\n\nEXISTING COPY TO EDIT:\n{request.content.strip()[:12000]}"

    prompt = f"""{_brand_context(brand)}

{_campaign_context(campaign) if campaign else 'No campaign brief selected. Keep the copy focused on the brand.'}

TASK: {action}
FORMAT: {kind_brief}
Tone: {request.tone}
{platform_line}
{length_line}
{extra}{existing}

Return only the finished copy. Do not explain what you did."""
    result = await generate_text(
        prompt,
        COPYWRITER_SYSTEM,
        temperature=0.8 if request.action in {"generate", "rewrite"} else 0.55,
        max_tokens=900,
        json_mode=False,
        operation=f"copy_{request.kind}_{request.action}",
    )
    content = result["content"].strip()
    if not content:
        raise ProviderError("The model returned empty copy. Try again.", status_code=502)
    return {
        "content": content,
        "provider": result["provider"],
        "model": result["model"],
        "duration_ms": result.get("duration_ms"),
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "kind": request.kind,
        "tone": request.tone,
    }

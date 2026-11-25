"""Natural-language explanations.

Always available: a templated explanation built purely from the score factors.
Optional: an LLM rewrite (Anthropic Claude or OpenAI) when an API key is configured. The LLM only
rephrases the numbers we hand it — it never invents stats — and any failure falls back to the template.
"""
import hashlib
import json
import logging
from typing import Dict, Optional

import httpx

from .. import config
from ..champions import name_of

log = logging.getLogger("draftmind.explain")
_cache: Dict[str, str] = {}

SYSTEM = (
    "You are an assistant coach for a professional League of Legends team. Explain a draft "
    "recommendation to the head coach in 2-3 short sentences. Use ONLY the facts and numbers provided; "
    "never invent statistics. Lead with the main reason, mention the main risk if one is listed, and keep "
    "it under 70 words. No preamble, no markdown."
)


def template_explanation(rec: dict, kind: str = "recommendation") -> str:
    """Deterministic explanation from the factor breakdown."""
    name = rec.get("name") or name_of(rec["champion"])
    factors = rec.get("factors", [])
    pos = [f for f in factors if f["contribution"] > 0.05]
    neg = [f for f in factors if f["contribution"] < -0.05]
    if kind == "prediction":
        head = f"{name} is a {round(100 * rec.get('probability', 0))}% likely opponent action"
    else:
        head = rec.get("summary") or name
        head = head.split(" — ")[0]
    parts = [head + "."]
    if pos:
        main = pos[0]
        parts.append(f"Biggest driver: {main['label'].lower()} — {main['evidence']}.")
        if len(pos) > 1:
            parts.append("Also: " + "; ".join(f"{f['label'].lower()} ({f['evidence']})" for f in pos[1:3]) + ".")
    if neg:
        parts.append(f"Watch out: {neg[0]['evidence']}.")
    return " ".join(parts)


def _facts(rec: dict, context: dict) -> str:
    lines = [f"Action: {context.get('action', 'pick')} {rec.get('name')} ({rec.get('role') or 'flex'})",
             f"Our team: {context.get('our_team')} vs opponent {context.get('opponent')}",
             f"Draft so far: {context.get('draft_so_far', 'start of draft')}"]
    if "score" in rec:
        lines.append(f"Fit score: {rec['score']}/100")
    if "probability" in rec:
        lines.append(f"Probability: {round(100 * rec['probability'])}%")
    for f in rec.get("factors", []):
        lines.append(f"- {f['label']}: contribution {f['contribution']:+.2f} | {f['evidence']}")
    return "\n".join(lines)


def _anthropic(prompt: str) -> Optional[str]:
    import anthropic  # optional dependency, imported lazily

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=30.0, max_retries=1)
    kwargs = dict(model=config.ANTHROPIC_MODEL, max_tokens=1024, system=SYSTEM,
                  messages=[{"role": "user", "content": prompt}])
    try:
        # Server-side refusal fallback + low effort for a short, fast answer.
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                           extra_body={"fallbacks": "default", "output_config": {"effort": "low"}},
                                           **kwargs)
    except anthropic.BadRequestError:
        resp = client.messages.create(**kwargs)  # model/config without those options
    if resp.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    return text or None


def _openai(prompt: str) -> Optional[str]:
    r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=30.0,
                   headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                   json={"model": config.OPENAI_MODEL,
                         "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip() or None


def explain(rec: dict, context: dict, kind: str = "recommendation") -> dict:
    templ = template_explanation(rec, kind)
    provider = config.llm_provider()
    if provider == "none":
        return {"text": templ, "source": "template", "template": templ}
    prompt = _facts(rec, context)
    key = hashlib.sha1((provider + prompt).encode()).hexdigest()
    if key in _cache:
        return {"text": _cache[key], "source": provider, "template": templ, "cached": True}
    try:
        text = _anthropic(prompt) if provider == "anthropic" else _openai(prompt)
    except Exception as e:  # noqa: BLE001 - never break the draft board over an LLM hiccup
        log.warning("LLM explanation failed (%s): %s", provider, e)
        text = None
    if not text:
        return {"text": templ, "source": "template", "template": templ, "llm_error": True}
    _cache[key] = text
    return {"text": text, "source": provider, "template": templ}


def facts_json(rec: dict) -> str:
    return json.dumps({f["key"]: f["evidence"] for f in rec.get("factors", [])})

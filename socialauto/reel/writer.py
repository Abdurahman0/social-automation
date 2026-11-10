"""Claude calls of the owner's flow: research, the 8-part script, rewrites from the owner's note, fix notes."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..lessons import Lessons, safe_fixed, safe_record
from . import research as research_mod
from . import script as script_mod

log = logging.getLogger(__name__)

LANG_NAMES = {"uz": "Uzbek (Latin script)", "ru": "Russian", "en": "English"}

FIX_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["summary", "title", "parts"],
    "properties": {
        "summary": {"type": "string", "description": "one line in Uzbek: what will change"},
        "title": {"type": ["string", "null"], "description": "new on-screen title, or null to keep it"},
        "parts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["part", "broll", "info", "subtitle_fix"],
            "properties": {
                "part": {"type": "string", "enum": list(script_mod.PARTS)},
                "broll": {"type": ["string", "null"], "description": "new English search words for real footage, or null"},
                "info": {"type": ["object", "null"], "additionalProperties": False, "required": ["value", "label"],
                         "properties": {"value": {"type": "string"}, "label": {"type": "string"}}},
                "subtitle_fix": {"type": ["string", "null"], "description": "corrected subtitle text of this part, or null"},
            }}},
    },
}


def system(niche: str, language: str) -> str:
    lang = LANG_NAMES.get(language, language)
    return (f"You are the writer of a vertical-video channel about {niche}. Video language: {lang}. The owner reads the "
            "narration aloud himself. Write for the ear: short sentences, plain words, numbers easy to say. Every fact "
            "comes from the given sources; never invent numbers. Answer only with the JSON object.")


def script_prompt(topic: dict, insight: str, wps: float) -> str:
    facts = "\n".join(f"- {f['claim']} ({f['source']}, {f.get('date', '')}, {f['url']})" for f in topic.get("facts", []))
    return (f"Write the reel script for this researched topic.\nTOPIC: {topic['title']}\nANGLE: {topic.get('angle', '')}\n"
            f"HOOK IDEA: {topic.get('hook_idea') or topic.get('hook', '')}\nVERIFIED FACTS:\n{facts}\n"
            f"WHAT WORKS ON THE ACCOUNT: {insight}\n\nRules (all must hold):\n"
            "- Exactly 8 parts in this order: hook, lead, body1, loop1, body2, loop2, body3, cta. loop1/loop2 are short "
            "open loops (a question or a promise that keeps people watching).\n"
            f"- {script_mod.window()[0]}-{script_mod.window()[1]} seconds spoken: {int(script_mod.window()[0] * wps)}-"
            f"{int(script_mod.window()[1] * wps)} words in total.\n"
            "- The answer or the strongest number is said in the FIRST sentence (first 5 seconds), written in DIGITS. key_fact = that number "
            "exactly as written in the hook.\n"
            "- After every technical term add a plain explanation starting with \"ya'ni\" (the double tap). List those "
            "terms in `terms`.\n"
            "- broll: 2-5 English words to find REAL footage or photos (water, pipes, treatment plant, river, city...). "
            "Never ask for animations, maps or illustrations.\n"
            "- info: a big number and a 2-5 word label for parts with a key figure, otherwise null.\n"
            "- title: max 45 characters, on screen for the whole video.\n- sources: the facts' sources (name + url).\n")


def brand_block(brand: dict | None) -> str:
    """Task 09: the user's own brand rules from his connected content repo (read-only), for every Claude call."""
    if not brand or not brand.get("text"):
        return ""
    return ("\n\nTHE AUTHOR'S OWN BRAND RULES (from his content repo; follow them — his voice, his CTA, his length, "
            "numbers only from sources; where they conflict with the format rules above, the format rules about the "
            "JSON shape win, his rules win about tone, length and wording):\n" + brand["text"])


class ReelWriter:
    def __init__(self, claude, niche: str, language: str, wps: float, lessons: Lessons | None = None,
                 context=None):
        self.claude = claude
        self.niche = niche
        self.language = language
        self.wps = wps
        self.lessons = lessons
        self.context = context            # () -> {"brand": dict | None, "examples": str} (the user's content repo)

    def _ctx(self) -> dict:
        if self.context is None:
            return {}
        try:
            return self.context() or {}
        except Exception:                 # noqa: BLE001 - his rules are extra context; never block a reel
            log.warning("content repo context not available", exc_info=True)
            return {}

    def _system(self) -> str:
        return system(self.niche, self.language) + brand_block(self._ctx().get("brand"))

    def research(self, insight_hint: str, avoid: list[str], today: date) -> dict:
        prompt = research_mod.prompt(self.niche, LANG_NAMES.get(self.language, self.language), insight_hint, avoid, today)
        examples = self._ctx().get("examples")
        if examples:
            prompt += ("\n\nThe author's own earlier reels and audit (examples only: do not repeat these topics; learn "
                       "which hooks and topics worked):\n" + examples)
        return self.claude.generate_json("research-topics", prompt, research_mod.SCHEMA, self._system(),
                                         tools=("WebSearch", "WebFetch"), timeout=900)

    def _checked(self, task: str, prompt: str) -> dict:
        draft = self.claude.generate_json(task, prompt, script_mod.SCHEMA, self._system())
        found = script_mod.problems(draft, self.wps)
        if not found:
            return draft
        ids = safe_record(self.lessons, "script", found)
        fixed = self.claude.generate_json(f"{task}-fix", prompt + "\n\nYour previous draft broke these rules; fix them "
                                          "and keep everything else:\n" + "\n".join(f"- {p}" for p in found) +
                                          "\n(For the first-5-seconds rule: write the key number in DIGITS inside the first sentence, e.g. \"1,7 million\", "
                                          "and copy exactly that into key_fact.)\nPrevious draft parts:\n" + "\n".join(f"{p['part']}: {p['text']}" for p in draft["parts"]),
                                          script_mod.SCHEMA, self._system())
        again = script_mod.problems(fixed, self.wps)
        if again:
            safe_record(self.lessons, "script", again)
            raise ValueError("the script broke the rules twice: " + "; ".join(again))
        safe_fixed(self.lessons, ids, "a corrective redraft naming the broken rules")
        return fixed

    def script(self, topic: dict, insight: str) -> dict:
        return self._checked("propose-reel-script", script_prompt(topic, insight, self.wps))

    def rewrite(self, current: dict, note: str) -> dict:
        prompt = ("Rewrite this reel script following the owner's note; keep what the note does not touch and keep all "
                  f"rules.\nOWNER'S NOTE: {note}\nCURRENT SCRIPT (JSON parts):\n" +
                  "\n".join(f"{p['part']}: {p['text']}" for p in current["parts"]) +
                  f"\nTITLE: {current['title']}\nKEY FACT: {current['key_fact']}\nSOURCES: " +
                  ", ".join(f"{s['name']} {s['url']}" for s in current.get("sources", [])) +
                  "\n\n" + script_prompt({"title": current["topic"], "facts": [], "hook_idea": current["key_fact"]}, "", self.wps))
        return self._checked("rewrite-reel-script", prompt)

    def restructure(self, current: dict, pasted: str) -> dict:
        """The owner pasted his own edited script that is not split into 8 parts: split it without changing words."""
        prompt = ("The owner edited the script himself. Split his text into the 8 parts WITHOUT changing, adding or "
                  "dropping words; fill broll/info/terms/key_fact/title/hashtags/sources from the old script where they "
                  f"still fit.\nOWNER'S TEXT:\n{pasted}\nOLD SCRIPT:\n" +
                  "\n".join(f"{p['part']}: {p['text']} [broll: {p['broll']}]" for p in current["parts"]) +
                  f"\nTITLE: {current['title']}\nSOURCES: " + ", ".join(f"{s['name']} {s['url']}" for s in current.get("sources", [])))
        return self.claude.generate_json("restructure-reel-script", prompt, script_mod.SCHEMA, self._system())

    def fix_plan(self, current: dict, note: str) -> dict:
        prompt = (f"The owner watched the reel and sent this fix note: {note}\nThe voice is already recorded, so the "
                  "spoken words cannot change; you may change the B-roll search words of a part, its infographic, the "
                  "on-screen title, or correct a part's subtitle text (spelling/terms). Only list parts that change.\n"
                  "CURRENT PARTS:\n" + "\n".join(f"{p['part']}: {p['text']} [broll: {p['broll']}] [info: {p.get('info')}]"
                                                for p in current["parts"]) + f"\nTITLE: {current['title']}")
        return self.claude.generate_json("reel-fix-plan", prompt, FIX_SCHEMA, self._system())

    def from_voice(self, spoken: str) -> dict:
        """The owner recorded a narration on his own: plan the 8 parts around EXACTLY his words."""
        prompt = ("The channel owner recorded this narration himself. Split it into the 8 parts (hook, lead, body1, "
                  "loop1, body2, loop2, body3, cta) WITHOUT changing, adding or dropping words, and write title, "
                  "key_fact (as said in the first sentence), terms, broll (English words for REAL footage), info, "
                  "hashtags and sources (only if the text names them; otherwise an empty list).\nSPOKEN TEXT:\n" + spoken)
        return self.claude.generate_json("plan-reel-from-voice", prompt, script_mod.SCHEMA, self._system())

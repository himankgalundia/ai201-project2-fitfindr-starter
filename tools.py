"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    estimate_price_fairness(item)                   → str  [stretch]
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive substring (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Price filter
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Size filter — case-insensitive substring match
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Build keyword set from description (alphanumeric tokens only)
    keywords = set(re.sub(r"[^a-z0-9\s]", "", description.lower()).split())

    def _score(listing: dict) -> int:
        # Concatenate all searchable text fields into one string
        searchable = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
            listing.get("brand", "") or "",
        ]).lower()
        tokens = set(re.sub(r"[^a-z0-9\s]", "", searchable).split())
        return len(keywords & tokens)

    scored = [(_score(l), l) for l in listings]
    # Drop listings with zero keyword overlap
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handled gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, returns general styling advice instead.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Unable to generate outfit suggestion: {e}"

    item_line = (
        f"{new_item.get('title', 'item')} "
        f"(${new_item.get('price', '?')}, "
        f"{new_item.get('condition', 'good')} condition, "
        f"size {new_item.get('size', 'unknown')})"
    )
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            "You are a personal stylist helping someone style a thrifted piece.\n\n"
            f"New item: {item_line}\n"
            f"Style tags: {item_tags}\n"
            f"Colors: {item_colors}\n\n"
            "The user hasn't entered their wardrobe yet. Give 1–2 specific outfit "
            "ideas for this piece, describing the types of items they could pair it "
            "with — name actual item types, silhouettes, and vibes. "
            "Be specific and casual, not generic. 3–5 sentences."
        )
    else:
        wardrobe_text = "\n".join(
            f"- {item['name']} "
            f"({item['category']}, colors: {', '.join(item.get('colors', []))}, "
            f"style: {', '.join(item.get('style_tags', []))})"
            + (f" — {item['notes']}" if item.get("notes") else "")
            for item in wardrobe_items
        )
        prompt = (
            "You are a personal stylist helping someone style a thrifted piece "
            "using their existing wardrobe.\n\n"
            f"New item: {item_line}\n"
            f"Style tags: {item_tags}\n"
            f"Colors: {item_colors}\n\n"
            f"Their wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1–2 specific outfit combinations using the new item plus "
            "named pieces from the wardrobe above. For each outfit, name the "
            "wardrobe pieces by their exact name and describe the vibe. "
            "Be specific and casual. 3–6 sentences total."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=350,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Unable to generate outfit suggestion right now. Please try again. ({e})"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence casual OOTD caption string.
        If outfit is empty or missing, returns a descriptive error string —
        does NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return (
            "Error: Cannot generate a fit card — outfit suggestion is missing. "
            "Please ensure suggest_outfit ran successfully first."
        )

    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Unable to generate fit card: {e}"

    item_name = new_item.get("title", "thrifted piece")
    price_raw = new_item.get("price", 0)
    item_price = int(price_raw) if isinstance(price_raw, float) and price_raw == int(price_raw) else price_raw
    platform = new_item.get("platform", "a secondhand app")

    prompt = (
        "You are writing a casual, authentic Instagram/TikTok OOTD caption "
        "for a thrifted outfit post.\n\n"
        f"Thrifted item: {item_name}\n"
        f"Price: ${item_price}\n"
        f"Platform: {platform}\n"
        f"Outfit description: {outfit}\n\n"
        "Write a 2–4 sentence caption that:\n"
        "- Sounds like a real person posting, not a brand\n"
        "- Mentions the item name, price, and platform naturally (once each)\n"
        "- Captures the outfit vibe in specific, concrete terms\n"
        "- Uses casual, lowercase-leaning language like real OOTD posts\n"
        "- Does NOT include hashtags\n\n"
        "Write only the caption text, nothing else."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Unable to generate fit card at this time. ({e})"


# ── Tool 4 (Stretch): estimate_price_fairness ─────────────────────────────────

def estimate_price_fairness(item: dict) -> str:
    """
    Estimate whether a listing's price is fair compared to similar items
    in the dataset (same category + overlapping style tags).

    Args:
        item: A listing dict. Uses id, category, style_tags, price, title.

    Returns:
        A human-readable verdict string — never raises an exception.
    """
    try:
        listings = load_listings()
    except Exception:
        return "Price check unavailable — could not load listings data."

    item_id = item.get("id", "")
    item_category = item.get("category", "")
    item_tags = set(item.get("style_tags", []))
    item_price = item.get("price", 0)
    item_title = item.get("title", "this item")

    # Find comparables: same category + at least 1 shared style tag
    comparables = [
        l for l in listings
        if l.get("id") != item_id
        and l.get("category") == item_category
        and bool(item_tags & set(l.get("style_tags", [])))
    ]

    # Fall back to same category only if no tag overlap found
    if not comparables:
        comparables = [
            l for l in listings
            if l.get("id") != item_id and l.get("category") == item_category
        ]

    if not comparables:
        return f"Not enough comparable listings to assess the price of {item_title}."

    avg_price = sum(l["price"] for l in comparables) / len(comparables)
    n = len(comparables)

    if item_price < avg_price * 0.8:
        verdict = "a great deal"
        detail = (
            f"It's ${item_price:.0f} vs. an average of ${avg_price:.0f} "
            f"for comparable items — you'd be saving about ${avg_price - item_price:.0f}."
        )
    elif item_price <= avg_price * 1.1:
        verdict = "a fair price"
        detail = (
            f"It's ${item_price:.0f}, right around the average of "
            f"${avg_price:.0f} for similar pieces."
        )
    else:
        verdict = "on the pricier side"
        detail = (
            f"It's ${item_price:.0f} vs. an average of ${avg_price:.0f} "
            f"for comparable items — you might find something similar for less."
        )

    return (
        f"Price check on {item_title}: This is {verdict}. "
        f"{detail} (Compared {n} similar listing{'s' if n != 1 else ''})"
    )

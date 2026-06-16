"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import create_fit_card, estimate_price_fairness, search_listings, suggest_outfit

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "price_assessment": None,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Parse a natural language clothing query into structured search parameters
    using the Groq LLM. Falls back to regex heuristics if the LLM call fails.

    Returns:
        dict with keys: description (str), size (str | None), max_price (float | None)
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        try:
            client = Groq(api_key=api_key)
            prompt = (
                "Extract search parameters from this clothing search query. "
                "Return ONLY valid JSON with exactly these keys:\n"
                '- "description": the clothing item being searched for (str, keep style descriptors, remove size/price mentions)\n'
                '- "size": the clothing size if mentioned (str like "M", "L", "XL", "S/M", or null)\n'
                '- "max_price": the maximum price if mentioned (number, or null)\n\n'
                f'Query: "{query}"\n\n'
                "JSON:"
            )
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=120,
            )
            text = response.choices[0].message.content.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    "description": str(parsed.get("description") or query),
                    "size": parsed.get("size") or None,
                    "max_price": float(parsed["max_price"]) if parsed.get("max_price") else None,
                }
        except Exception:
            pass  # fall through to regex fallback

    # Regex fallback
    max_price = None
    price_match = re.search(
        r"(?:under|below|max|less than|up to|at most|no more than)\s*\$?\s*(\d+(?:\.\d+)?)",
        query,
        re.IGNORECASE,
    )
    if not price_match:
        price_match = re.search(r"\$(\d+(?:\.\d+)?)\s*(?:or less|max)", query, re.IGNORECASE)
    if price_match:
        max_price = float(price_match.group(1))

    size = None
    size_match = re.search(
        r"(?:size\s+|in\s+(?:a\s+)?)(XS|S|M|L|XL|XXL|XXXL|Small|Medium|Large)",
        query,
        re.IGNORECASE,
    )
    if not size_match:
        size_match = re.search(r"\b(XS|XXL|XXXL)\b", query, re.IGNORECASE)
    if size_match:
        size = size_match.group(1).upper()

    # Clean description by stripping price and size phrases
    desc = query
    desc = re.sub(
        r"(?:under|below|max|less than|up to|at most|no more than)\s*\$?\s*\d+(?:\.\d+)?",
        "",
        desc,
        flags=re.IGNORECASE,
    )
    desc = re.sub(r"\$\d+(?:\.\d+)?\s*(?:or less|max)?", "", desc, flags=re.IGNORECASE)
    desc = re.sub(
        r"(?:size\s+|in\s+(?:a\s+)?)(XS|S|M|L|XL|XXL|XXXL|Small|Medium|Large)",
        "",
        desc,
        flags=re.IGNORECASE,
    )
    desc = re.sub(r"\s+", " ", desc).strip().strip(",").strip()

    return {
        "description": desc if desc else query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop:
      1. Initialize session
      2. Parse query → description, size, max_price
      3. search_listings() → if empty, set error and return early
      4. Select top result as selected_item
      5. estimate_price_fairness() [stretch]
      6. suggest_outfit()
      7. create_fit_card()
      8. Return session

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion / fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into structured search parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    # Step 3: Search listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    if not results:
        parts = [f"No listings found for '{description}'"]
        if size:
            parts[0] += f" in size {size}"
        if max_price is not None:
            parts[0] += f" under ${max_price:.0f}"
        parts.append(
            "Try broader keywords, removing the size filter, or increasing your budget."
        )
        session["error"] = " — ".join(parts)
        return session

    # Step 4: Select the top result
    session["selected_item"] = results[0]
    selected = session["selected_item"]

    # Step 5: Price check (stretch feature)
    session["price_assessment"] = estimate_price_fairness(selected)

    # Step 6: Suggest outfit
    session["outfit_suggestion"] = suggest_outfit(selected, wardrobe)

    # Step 7: Create fit card
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], selected)

    # Step 8: Return session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_empty_wardrobe, get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"Parsed: {session['parsed']}")
        print(f"\nPrice: {session['price_assessment']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    print(f"fit_card is None: {session2['fit_card'] is None}")

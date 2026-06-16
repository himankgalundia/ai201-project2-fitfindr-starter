# FitFindr

A thrift-shopping AI agent that finds secondhand clothing listings, suggests outfits using your existing wardrobe, and generates shareable fit card captions — all in one multi-step planning loop.

---

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tools.py                   # All tool implementations
├── agent.py                   # Planning loop (run_agent)
├── app.py                     # Gradio UI
├── tests/
│   └── test_tools.py          # Pytest tests for each tool
├── planning.md                # Spec and agent diagram
└── requirements.txt           # Python dependencies
```

---

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Run tests:
```bash
pytest tests/
```

---

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

---

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`

Searches the mock listings dataset for clothing items matching the description, optional size, and optional price ceiling. Scores each listing by keyword overlap across `title`, `description`, `style_tags`, `category`, `colors`, and `brand`. Returns results sorted by relevance score, highest first. Returns `[]` if nothing matches — never raises an exception.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Natural language keywords (e.g., `"vintage graphic tee"`) |
| `size` | `str \| None` | Size filter, case-insensitive substring match (e.g., `"M"`). `None` skips size filtering. |
| `max_price` | `float \| None` | Maximum price inclusive (e.g., `30.0`). `None` skips price filtering. |

**Returns:** `list[dict]` — each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

---

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

Given a thrifted listing and the user's wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations. If the wardrobe has items, names specific pieces from it by their `name` field. If the wardrobe is empty, provides general styling advice instead — never crashes.

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict (the item the user is considering buying) |
| `wardrobe` | `dict` | A wardrobe dict with an `'items'` key (list of wardrobe item dicts). May be empty. |

**Returns:** `str` — 3–6 sentence outfit suggestion. Never empty.

---

### `create_fit_card(outfit: str, new_item: dict) → str`

Generates a casual OOTD caption (2–4 sentences) suitable for Instagram or TikTok. Uses `temperature=1.0` to produce different output each run. Guards against an empty `outfit` string before calling the LLM.

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit()`. Must be non-empty. |
| `new_item` | `dict` | The listing dict. Uses `title`, `price`, `platform` in the caption. |

**Returns:** `str` — 2–4 sentence caption, or a descriptive error string if `outfit` is empty.

---

### `estimate_price_fairness(item: dict) → str` *(stretch)*

Compares a listing's price against comparable items in the dataset (same category + at least one overlapping style tag) and returns a plain-English verdict.

| Parameter | Type | Description |
|-----------|------|-------------|
| `item` | `dict` | A listing dict. Uses `id`, `category`, `style_tags`, `price`, `title`. |

**Returns:** `str` — e.g., `"Price check on Y2K Baby Tee: This is a fair price. It's $18, right around the average of $22 for similar pieces. (Compared 14 similar listings)"`

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in `agent.py` follows these steps:

1. **Parse** — `_parse_query(query)` calls the LLM to extract `description`, `size`, and `max_price` from the natural language query (with a regex fallback if the LLM call fails). Result stored in `session["parsed"]`.

2. **Search** — `search_listings(description, size, max_price)` is called. If it returns an empty list, the loop sets `session["error"]` to a specific, actionable message and **returns immediately** — `suggest_outfit` and `create_fit_card` are never called with empty input.

3. **Select** — `session["selected_item"]` is set to `results[0]`, the highest-relevance listing.

4. **Price check** *(stretch)* — `estimate_price_fairness(selected_item)` runs unconditionally and stores a verdict string in `session["price_assessment"]`.

5. **Outfit** — `suggest_outfit(selected_item, wardrobe)` is called. The tool itself branches internally: empty wardrobe triggers a general styling prompt; a populated wardrobe triggers a wardrobe-specific prompt. Result stored in `session["outfit_suggestion"]`.

6. **Fit card** — `create_fit_card(session["outfit_suggestion"], selected_item)` is called. Result stored in `session["fit_card"]`.

7. **Return** — the full session dict is returned to `app.py`, which maps each key to a Gradio output panel.

The key conditional is at step 2: the loop does not call all three tools unconditionally — it terminates early and sets an error if search returns nothing.

---

## State Management

All state lives in a single `session` dict initialized by `_new_session()` at the start of each interaction. No value is re-entered by the user or hard-coded between steps.

| Key | Written by | Read by |
|-----|-----------|---------|
| `session["query"]` | `_new_session()` | `_parse_query()` |
| `session["parsed"]` | `_parse_query()` | `search_listings()` call |
| `session["search_results"]` | `search_listings()` | step 3 (select top item) |
| `session["selected_item"]` | step 3 | `suggest_outfit()`, `create_fit_card()`, `estimate_price_fairness()` |
| `session["wardrobe"]` | `_new_session()` | `suggest_outfit()` |
| `session["price_assessment"]` | `estimate_price_fairness()` | `app.py` (display in panel 1) |
| `session["outfit_suggestion"]` | `suggest_outfit()` | `create_fit_card()` |
| `session["fit_card"]` | `create_fit_card()` | `app.py` (display in panel 3) |
| `session["error"]` | step 2 (no-results branch) | `app.py` (shows error, leaves panels 2–3 blank) |

The item found by `search_listings` flows into `suggest_outfit` and then `create_fit_card` through the session dict — the user never re-enters it.

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30"`

**Step 1 — Tool called: `_parse_query` + `search_listings`**

- Tool: `search_listings`
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why this tool: The agent always starts by searching — it can't suggest an outfit without a concrete item.
- Output: A list of matching listings sorted by relevance. Top result: Y2K Baby Tee — Butterfly Print, $18, depop, size S/M.

**Step 2 — Tool called: `suggest_outfit`**

- Tool: `suggest_outfit`
- Input: `new_item=<Y2K Baby Tee dict>`, `wardrobe=<example wardrobe with 10 items>`
- Why this tool: The search returned a result, so the agent proceeds to styling. The selected item from step 1 passes directly into this tool via `session["selected_item"]` — no re-entry.
- Output: "Pair the Y2K Baby Tee with your Baggy straight-leg jeans and Chunky white sneakers for a laid-back streetwear look. Alternatively, try it with your Wide-leg khaki trousers and Black combat boots for a more earthy, eclectic vibe."

**Step 3 — Tool called: `create_fit_card`**

- Tool: `create_fit_card`
- Input: `outfit=<suggestion from step 2>`, `new_item=<Y2K Baby Tee dict>`
- Why this tool: The outfit suggestion from step 2 passes directly into this tool — the agent uses `session["outfit_suggestion"]` without asking the user to re-describe anything.
- Output: "just scored this y2k baby tee on depop for $18 and it goes with literally everything. baggy jeans and chunky sneakers is the move every time."

**Final output to user:**
- Panel 1: Item details (title, price, platform, size, condition, style tags) + price fairness assessment
- Panel 2: Outfit suggestion naming specific wardrobe pieces
- Panel 3: Casual OOTD caption ready to post

---

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | Returns `[]` — no listings match the query | Planning loop sets `session["error"]` = "No listings found for '[description]' in size [size] under $[price] — Try broader keywords, removing the size filter, or increasing your budget." Returns immediately; `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit` | `wardrobe['items']` is empty (new user) | Uses a different LLM prompt that asks for general styling advice — types of items, silhouettes, and vibes that pair well — instead of wardrobe-specific combinations. Returns a non-empty string; never crashes. |
| `create_fit_card` | `outfit` argument is empty or whitespace-only | Returns the string `"Error: Cannot generate a fit card — outfit suggestion is missing."` immediately, without calling the LLM. Does not raise an exception. |

**Concrete test example — triggering `search_listings` failure:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```
Running the full agent with `"designer ballgown size XXS under $5"` produces: `"No listings found for 'designer ballgown' in size XXS under $5 — Try broader keywords, removing the size filter, or increasing your budget."` Panels 2 and 3 remain blank.

---

## Spec Reflection

**One way planning.md helped during implementation:**
The architecture diagram with the explicit early-exit branch made it clear that `suggest_outfit` should never receive an empty list. Without the diagram, it would have been easy to pass empty input through and let the LLM produce a nonsensical "outfit" for nothing. Having the branch documented meant the condition check was the first thing written in `run_agent()`.

**One divergence from the spec, and why:**
The spec described query parsing as a simple regex step, but the implementation uses an LLM call (with regex as a fallback). Regex worked for structured inputs like "vintage tee under $30, size M" but failed on natural queries like "I'm looking for something grunge-y and cheap" — there's no price or size marker to match. Switching to LLM parsing handled the full range of natural language inputs the Gradio demo accepts, which was the actual use case.

---

## AI Usage

**Instance 1 — Implementing `search_listings`:**
I gave Claude the Tool 1 spec from planning.md (inputs, return value, failure mode) and asked it to implement keyword scoring using set intersection across title, description, style_tags, category, colors, and brand fields. The generated code used `re.sub` to strip punctuation before tokenizing — I kept that approach because it correctly handled hyphenated tags like "graphic-tee". I revised the score threshold: the initial version kept listings with score ≥ 1, which I kept, but I added an explicit `if s > 0` filter to make the zero-drop step clear rather than relying on the sort implicitly excluding them.

**Instance 2 — Implementing the planning loop in `agent.py`:**
I gave Claude the architecture diagram from planning.md and asked it to implement `run_agent()` with the exact conditional step sequence shown — including the early-exit branch at step 2. The generated code had all three tools called unconditionally (no branch on empty results). I overrode this by adding the explicit `if not results:` check that sets `session["error"]` and returns early, which is the core behavioral requirement of the planning loop. I also added the regex fallback to `_parse_query()` myself — the generated version had no fallback and would crash if the Groq API was unavailable.

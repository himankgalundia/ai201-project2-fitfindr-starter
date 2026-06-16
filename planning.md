# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for clothing items matching a natural language description, optional size filter, and optional price ceiling. Scores each listing by keyword overlap and returns matches sorted by relevance, highest first. Returns an empty list if nothing matches — never raises an exception.

**Input parameters:**
- `description` (str): Natural language keywords describing what the user wants (e.g., "vintage graphic tee"). Scored against each listing's title, description, style_tags, category, colors, and brand.
- `size` (str | None): Size string to filter by (e.g., "M", "XL"). Case-insensitive substring match against the listing's `size` field. Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price inclusive (e.g., 30.0). Listings with `price > max_price` are excluded. Pass `None` to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str). Returns `[]` if no listings match.

**What happens if it fails or returns nothing:**
Returns `[]` — never raises. The planning loop checks: if `results == []`, it sets `session["error"]` to a specific message (e.g., "No listings found for 'designer ballgown' in size XXS under $5 — Try broader keywords, removing the size filter, or increasing your budget.") and returns the session immediately without calling `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted listing and the user's wardrobe, calls the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfit combinations. If the wardrobe has items, names specific pieces from it by name. If the wardrobe is empty, generates general styling advice for the item type instead — never crashes or returns an empty string.

**Input parameters:**
- `new_item` (dict): A listing dict (the item the user is considering buying). Uses `title`, `price`, `size`, `condition`, `style_tags`, `colors` to build the LLM prompt.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key (list of wardrobe item dicts, each with `name`, `category`, `colors`, `style_tags`, `notes`). The list may be empty.

**What it returns:**
A non-empty string (3–6 sentences) with 1–2 specific outfit suggestions. When the wardrobe is populated, names actual wardrobe pieces by their `name` field. When the wardrobe is empty, describes item types, silhouettes, and vibes that pair well with the new item.

**What happens if it fails or returns nothing:**
- Empty `wardrobe['items']`: uses an alternate LLM prompt for general styling advice. Does not crash or return `""`.
- Groq API error: catches the exception and returns the string `"Unable to generate outfit suggestion right now. Please try again."` — never re-raises.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual Instagram/TikTok-style OOTD caption (2–4 sentences) based on the outfit suggestion and the item's details. Uses LLM temperature=1.0 to ensure outputs vary across runs. Guards against an empty outfit string before calling the LLM.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`. Must be non-empty for the LLM call to proceed.
- `new_item` (dict): The listing dict for the thrifted item. Uses `title`, `price`, `platform` to anchor the caption in real details.

**What it returns:**
A 2–4 sentence string in casual OOTD caption style. Mentions the item name, price, and platform naturally once each. Varies across runs due to temperature=1.0.

**What happens if it fails or returns nothing:**
- Empty or whitespace-only `outfit`: immediately returns `"Error: Cannot generate a fit card — outfit suggestion is missing."` without calling the LLM.
- Groq API error: catches the exception and returns `"Unable to generate fit card at this time."` — never re-raises.

---

### Additional Tools (if any)

### Tool 4 (Stretch): estimate_price_fairness

**What it does:**
Given a listing item, scans the full listings dataset to find comparable items (same category + at least one overlapping style tag) and compares the item's price against the average comparable price. Returns a verdict: "a great deal", "a fair price", or "on the pricier side", with a dollar comparison.

**Input parameters:**
- `item` (dict): A listing dict. Uses `id`, `category`, `style_tags`, `price`, `title`.

**What it returns:**
A human-readable string, e.g.: `"Price check on Graphic Tee — 2003 Tour Bootleg Style: This is a great deal. It's $24 vs. an average of $36 for comparable items — you'd be saving about $12. (Compared 7 similar listings)"`. Never raises.

**What happens if it fails or returns nothing:**
If no comparable listings exist, falls back to same-category-only comparison. If that also returns nothing, returns `"Not enough comparable listings to assess the price of [title]."`.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop in `run_agent()` follows these conditional steps:

1. Parse the query with `_parse_query()` to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.
2. Call `search_listings(description, size, max_price)`. Store results in `session["search_results"]`.
   - **If results is empty**: set `session["error"]` to a specific, actionable message and `return session` immediately. `suggest_outfit` and `create_fit_card` are **skipped**.
   - **If results is non-empty**: continue.
3. Set `session["selected_item"] = results[0]` (highest relevance score).
4. Call `estimate_price_fairness(selected_item)`. Store in `session["price_assessment"]` (stretch).
5. Call `suggest_outfit(selected_item, wardrobe)`. Store in `session["outfit_suggestion"]`.
6. Call `create_fit_card(session["outfit_suggestion"], selected_item)`. Store in `session["fit_card"]`.
7. Return the session.

The loop is not fixed-sequence: it only proceeds to steps 5–7 if step 2 returns results.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()`. Each step writes its output into a specific key, and the next step reads from that key — no value is re-entered by the user or hard-coded between calls:

- `session["parsed"]` ← output of `_parse_query()`, read by `search_listings()`
- `session["search_results"]` ← output of `search_listings()`, used to set `selected_item`
- `session["selected_item"]` ← `results[0]`, passed into `suggest_outfit()`, `create_fit_card()`, and `estimate_price_fairness()`
- `session["outfit_suggestion"]` ← output of `suggest_outfit()`, passed directly into `create_fit_card()`
- `session["fit_card"]` ← output of `create_fit_card()`, returned to `app.py`
- `session["error"]` ← set on early exit, read by `app.py` to decide which panels to populate

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (returns `[]`) | Planning loop sets `session["error"]` to "No listings found for '[description]'[size clause][price clause] — Try broader keywords, removing the size filter, or increasing your budget." and returns immediately. `suggest_outfit` is never called. |
| suggest_outfit | `wardrobe['items']` is empty | Uses an alternate LLM prompt asking for general styling advice (item types, silhouettes, vibes). Returns a useful suggestion string — never crashes or returns `""`. |
| create_fit_card | `outfit` argument is empty or whitespace-only | Returns the string `"Error: Cannot generate a fit card — outfit suggestion is missing."` immediately without calling the LLM. Does not raise an exception. |

---

## Architecture

```
User query (natural language)
    │
    ▼
Planning Loop — run_agent(query, wardrobe)
    │
    ├─ Step 1: _parse_query(query)  [LLM call]
    │       └──► session["parsed"] = {description, size, max_price}
    │
    ├─ Step 2: search_listings(description, size, max_price)
    │       │
    │       │  results == []
    │       ├──────────────► session["error"] = "No listings found..."
    │       │                return session  ◄── early exit
    │       │
    │       │  results = [item, ...]
    │       └──► session["search_results"] = [...]
    │
    ├─ Step 3: select top result
    │       └──► session["selected_item"] = results[0]
    │
    ├─ Step 4 (stretch): estimate_price_fairness(selected_item)
    │       └──► session["price_assessment"] = "Price check: ..."
    │
    ├─ Step 5: suggest_outfit(selected_item, wardrobe)
    │       │
    │       │  wardrobe empty?
    │       ├──────────────► LLM prompt: general styling advice
    │       │
    │       │  wardrobe populated?
    │       └──────────────► LLM prompt: specific outfit combos from wardrobe
    │               └──► session["outfit_suggestion"] = "..."
    │
    └─ Step 6: create_fit_card(outfit_suggestion, selected_item)
            │  outfit empty?
            ├──────────────► return error string (no LLM call)
            │
            └──────────────► LLM call (temperature=1.0)
                    └──► session["fit_card"] = "..."
    │
    ▼
Return session → app.py → Gradio UI (3 output panels)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: I gave Claude the Tool 1 spec (inputs, return value, failure mode) and the `load_listings()` signature, and asked it to implement keyword scoring using set intersection across title, description, style_tags, category, colors, and brand. I verified by testing with "designer ballgown under $5 XXS" (must return `[]`) and "vintage graphic tee under $30" (must return ≥1 result with price ≤ $30).

For `suggest_outfit`: I gave Claude the Tool 2 spec, the wardrobe schema structure, and the `_get_groq_client()` pattern. I asked it to implement two prompt branches (empty wardrobe vs. populated). I verified the empty-wardrobe path doesn't crash using `get_empty_wardrobe()` and that the populated path names actual wardrobe items.

For `create_fit_card`: I gave Claude the Tool 3 spec and asked it to use `temperature=1.0` for variety and guard against empty outfit strings. I ran it multiple times on the same input and confirmed outputs differed. I also tested the empty-outfit guard returns a string, not an exception.

For `estimate_price_fairness` (stretch): I gave Claude the Tool 4 spec and asked it to compare same-category + overlapping-style-tag listings and return a verdict string. I verified it handles the zero-comparables edge case.

**Milestone 4 — Planning loop and state management:**

I gave Claude the Architecture diagram and Planning Loop spec above, and asked it to implement `run_agent()` with these exact conditional steps and LLM-based query parsing with a regex fallback. I verified by running `python agent.py` directly: confirmed `session["selected_item"]` is non-None on the happy path, and that `session["error"]` is set with `fit_card=None` on the no-results path.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
`_parse_query()` sends the query to the LLM and receives `{description: "vintage graphic tee", size: null, max_price: 30.0}`. Stored in `session["parsed"]`. Then `search_listings("vintage graphic tee", size=None, max_price=30.0)` is called. It loads all listings, filters to those with `price ≤ 30`, and scores by keyword overlap with {"vintage", "graphic", "tee"}. Returns 3+ results sorted by score. `session["search_results"]` is populated; `session["selected_item"]` is set to the top result (e.g., Y2K Baby Tee — $18, depop).

**Step 2:**
`suggest_outfit(selected_item, example_wardrobe)` is called with the Y2K Baby Tee dict and the 10-item example wardrobe. The LLM prompt lists all wardrobe pieces and asks for specific outfit combinations. Returns: "Pair the Y2K Baby Tee with your Baggy straight-leg jeans and Chunky white sneakers for a laid-back streetwear look. Alternatively, try it with your Wide-leg khaki trousers and Black combat boots for a more eclectic, earthy vibe." Stored in `session["outfit_suggestion"]`.

**Step 3:**
`create_fit_card(outfit_suggestion, selected_item)` is called with the outfit string and the item dict. The LLM generates a casual OOTD caption at temperature=1.0. Returns: "just scored this y2k baby tee on depop for $18 and it goes with literally everything in my closet. baggy jeans and chunky sneakers is the move but i'm also eyeing the khaki trouser combo." Stored in `session["fit_card"]`.

**Final output to user:**
Three panels display: (1) the item details + price assessment, (2) the outfit suggestion naming specific wardrobe pieces, (3) the fit card caption.

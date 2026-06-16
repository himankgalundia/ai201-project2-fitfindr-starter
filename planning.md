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
Searches the mock listings dataset for clothing items matching a natural language description, optional size filter, and optional price ceiling. Returns a relevance-sorted list of matching listing dicts — most keyword overlap with the description comes first. Returns an empty list (never raises) if nothing matches.

**Input parameters:**
- `description` (str): Natural language keywords describing what the user wants (e.g., "vintage graphic tee"). Scored against each listing's title, description, style_tags, category, colors, and brand fields.
- `size` (str | None): Size string to filter by (e.g., "M", "XL", "W30 L30"). Case-insensitive substring match against listing's `size` field. Pass `None` to skip size filtering entirely.
- `max_price` (float | None): Maximum price inclusive (e.g., 30.0). Listings with `price > max_price` are excluded. Pass `None` to skip price filtering.

**What it returns:**
A list of listing dicts, each containing: `id` (str), `title` (str), `description` (str), `category` (str — one of tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str — depop/thredUp/poshmark). Sorted descending by keyword relevance score. Returns `[]` if no listings match.

**What happens if it fails or returns nothing:**
Returns `[]` — never raises. The planning loop checks: `if not results`, sets `session["error"]` to a specific message like `"No listings found for 'designer ballgown' in size XXS under $5. Try broader keywords, removing the size filter, or increasing your budget."`, and returns the session early. `suggest_outfit` is never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted listing and the user's current wardrobe, calls the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfit combinations. If the wardrobe has items, names specific pieces from it. If the wardrobe is empty, generates general styling advice for the item type instead — never crashes.

**Input parameters:**
- `new_item` (dict): A listing dict (the item the user is considering buying). Uses `title`, `price`, `size`, `condition`, `style_tags`, `colors` to build the LLM prompt.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key (list of wardrobe item dicts). Each wardrobe item has `name`, `category`, `colors`, `style_tags`, `notes`. The list may be empty.

**What it returns:**
A non-empty string (3–6 sentences) with 1–2 specific outfit suggestions. When the wardrobe is populated, names actual wardrobe pieces by their `name` field. When the wardrobe is empty, describes item types and silhouettes that pair well with the new item.

**What happens if it fails or returns nothing:**
- Empty `wardrobe['items']`: uses an alternate LLM prompt for general styling advice. Does not crash or return `""`.
- Groq API error: catches the exception and returns the string `"Unable to generate outfit suggestion right now. Please try again."` — never re-raises.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual Instagram/TikTok-style OOTD caption (2–4 sentences) based on the outfit suggestion and the item's details. Uses LLM temperature=1.0 to ensure outputs vary across different inputs. Guards against an empty outfit string before calling the LLM.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`. Must be non-empty for the LLM call to proceed.
- `new_item` (dict): The listing dict for the thrifted item. Uses `title`, `price`, `platform` to anchor the caption in real details.

**What it returns:**
A 2–4 sentence string in casual OOTD caption style (lowercase-leaning, no hashtags). Mentions the item name, price, and platform naturally once each. Captures the outfit vibe in specific terms. Varies across different inputs due to temperature=1.0.

**What happens if it fails or returns nothing:**
- Empty or whitespace-only `outfit`: immediately returns `"Error: Cannot generate a fit card — outfit suggestion is missing. Please ensure suggest_outfit ran successfully."` without calling the LLM.
- Groq API error: catches the exception and returns `"Unable to generate fit card at this time."` — never re-raises.

---

### Additional Tools

### Tool 4 (Stretch): estimate_price_fairness

**What it does:**
Given a listing item, scans the full listings dataset to find comparable items (same category, at least one overlapping style tag) and compares the item's price against the average comparable price. Returns a verdict: "great deal", "fair price", or "on the pricier side".

**Input parameters:**
- `item` (dict): A listing dict. Uses `id`, `category`, `style_tags`, `price`, `title`.

**What it returns:**
A human-readable string like: `"Price check on Graphic Tee — 2003 Tour Bootleg Style: This is a great deal. It's $24 vs. an average of $36 for comparable items — you'd be saving about $12. (Compared 7 similar listings)"`. Never raises.

**What happens if it fails or returns nothing:**
If no comparable listings exist, falls back to same-category-only comparison. If that also fails, returns `"Not enough comparable listings to assess the price of [title]."`.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` executes the following conditional steps:

1. **Initialize session**: Call `_new_session(query, wardrobe)`. All output fields start as `None`.

2. **Parse query**: Call `_parse_query(query)` which uses the Groq LLM to extract a structured `{description, size, max_price}` dict from the natural language query. Store result in `session["parsed"]`. On parse failure, fall back to using the full query as `description` with `size=None`, `max_price=None`.

3. **Search**: Call `search_listings(description, size, max_price)`. Store result in `session["search_results"]`.
   - **Branch — no results**: if `results == []`, set `session["error"]` to a specific, actionable message and `return session` immediately. Steps 4–7 are **skipped**. The agent does not call `suggest_outfit` with empty input.
   - **Branch — results found**: continue to step 4.

4. **Select item**: Set `session["selected_item"] = session["search_results"][0]` (highest relevance score).

5. **Price check (stretch)**: Call `estimate_price_fairness(selected_item)`. Store in `session["price_assessment"]`. This step always succeeds (returns a string).

6. **Outfit suggestion**: Call `suggest_outfit(selected_item, wardrobe)`. Store in `session["outfit_suggestion"]`. Handles empty wardrobe internally.

7. **Fit card**: Call `create_fit_card(session["outfit_suggestion"], selected_item)`. Store in `session["fit_card"]`. Handles missing outfit string internally.

8. **Return session**.

The loop is not a fixed sequence — it branches at step 3. Only if `search_listings` returns results does it proceed to `suggest_outfit` and `create_fit_card`.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()`. Each step writes into a specific key, and the next step reads from that key — no value is re-entered by the user or hard-coded between calls:

| Key | Written by | Read by |
|-----|-----------|---------|
| `session["query"]` | `_new_session()` | `_parse_query()` |
| `session["parsed"]` | `_parse_query()` | `search_listings()` (extracts description/size/max_price) |
| `session["search_results"]` | `search_listings()` | Step 4 (select top item) |
| `session["selected_item"]` | Step 4 | `suggest_outfit()`, `create_fit_card()`, `estimate_price_fairness()` |
| `session["wardrobe"]` | `_new_session()` | `suggest_outfit()` |
| `session["price_assessment"]` | `estimate_price_fairness()` | `app.py` (display) |
| `session["outfit_suggestion"]` | `suggest_outfit()` | `create_fit_card()` |
| `session["fit_card"]` | `create_fit_card()` | `app.py` (display) |
| `session["error"]` | Step 3 (no-results branch) | `app.py` (display) |

The session is passed by reference through the planning loop. `app.py`'s `handle_query()` receives the final session dict and maps each key to the appropriate output panel.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match the query (returns `[]`) | Planning loop sets `session["error"] = "No listings found for '[description]'[size clause][price clause]. Try broader keywords, removing the size filter, or increasing your budget."` and returns the session immediately. `suggest_outfit` is never called. |
| suggest_outfit | `wardrobe['items']` is empty (new user) | Uses an alternate LLM prompt that asks for general styling advice (item types, silhouettes, vibes that pair well) instead of wardrobe-specific combinations. Returns a useful suggestion string — never crashes or returns `""`. |
| create_fit_card | `outfit` argument is empty or whitespace-only | Returns the string `"Error: Cannot generate a fit card — outfit suggestion is missing."` immediately without calling the LLM. Does not raise an exception. |

---

## Architecture

```
User query (natural language)
    │
    ▼
Planning Loop — run_agent(query, wardrobe)
    │
    ├─ Step 2: _parse_query(query)  [LLM call]
    │       └──► session["parsed"] = {description, size, max_price}
    │
    ├─ Step 3: search_listings(description, size, max_price)
    │       │
    │       │  results == []
    │       ├──────────────► session["error"] = "No listings found..."
    │       │                return session  ◄── early exit
    │       │
    │       │  results = [item, ...]
    │       └──► session["search_results"] = [...]
    │
    ├─ Step 4: select top result
    │       └──► session["selected_item"] = results[0]
    │
    ├─ Step 5 (stretch): estimate_price_fairness(selected_item)
    │       └──► session["price_assessment"] = "Price check: ..."
    │
    ├─ Step 6: suggest_outfit(selected_item, wardrobe)
    │       │
    │       │  wardrobe empty?
    │       ├──────────────► LLM prompt: general styling advice
    │       │
    │       │  wardrobe populated?
    │       ├──────────────► LLM prompt: specific outfit combos from wardrobe
    │       │
    │       └──► session["outfit_suggestion"] = "..."
    │
    └─ Step 7: create_fit_card(outfit_suggestion, selected_item)
            │
            │  outfit empty?
            ├──────────────► return error string (no LLM call)
            │
            │  outfit populated?
            └──────────────► LLM call (temperature=1.0)
                    └──► session["fit_card"] = "..."
    │
    ▼
Return session dict
    │
    ▼
app.py — handle_query()
    │
    ├── session["error"] set?  ──► return (error_msg, "", "")
    │
    └── success path  ──► format selected_item + price_assessment → listing_text
                      └── return (listing_text, outfit_suggestion, fit_card)
    │
    ▼
Gradio UI — three output panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: I used Claude with the Tool 1 spec (inputs, return value, failure mode) and the `load_listings()` signature. I asked it to implement keyword scoring across title, description, style_tags, category, colors, and brand using set intersection. I verified by testing with "designer ballgown under $5 XXS" (must return `[]`) and "vintage graphic tee under $30" (must return ≥1 result with price ≤ $30).

For `suggest_outfit`: I used Claude with the Tool 2 spec, the wardrobe schema structure, and the Groq API pattern from `_get_groq_client()`. I asked it to implement two prompt branches. I verified the empty-wardrobe path doesn't crash using `get_empty_wardrobe()` and that the populated-wardrobe path names actual wardrobe items from the example wardrobe.

For `create_fit_card`: I used Claude with the Tool 3 spec. I asked it to use `temperature=1.0` for variety and guard against empty outfit strings. I ran it 3× on the same input and confirmed outputs differed. I also tested the empty-outfit guard.

For `estimate_price_fairness` (stretch): I used Claude with the Tool 4 spec and asked it to find comparables by category + overlapping style tags, compute the mean price, and return a verdict string. I verified it handles zero-comparables edge case.

**Milestone 4 — Planning loop and state management:**

I used Claude with the Architecture diagram and Planning Loop spec above. I asked it to implement `run_agent()` with the exact 7-step conditional flow, using LLM parsing for query extraction. I verified by running `python agent.py` and checking that `session["selected_item"]` is non-None on the happy path, and that `session["error"]` is set with `fit_card=None` on the no-results path ("designer ballgown size XXS under $5").

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse query:**
`_parse_query()` sends the query to the LLM and receives `{description: "vintage graphic tee", size: null, max_price: 30.0}`. Stored in `session["parsed"]`.

**Step 2 — Search:**
`search_listings("vintage graphic tee", size=None, max_price=30.0)` is called. It loads all listings, keeps those with `price ≤ 30`, and scores by keyword overlap with {"vintage", "graphic", "tee"}. Matching listings include:
- lst_006 Graphic Tee — 2003 Tour Bootleg ($24) — score 3 (graphic tee, vintage in tags)
- lst_002 Y2K Baby Tee — Butterfly Print ($18) — score 2 (graphic tee, vintage in tags)
- lst_009 Washed Black Band Tee ($20) — score 2 (vintage, band tee in tags)

Returns 3+ results sorted by score. `session["search_results"]` = [lst_006, lst_002, ...]. `session["selected_item"]` = lst_006.

**Step 3 — Price check:**
`estimate_price_fairness(lst_006)` scans all tops with overlapping style tags. Average comparable price ~$28. Returns "Price check on Graphic Tee — 2003 Tour Bootleg Style: This is a fair price. It's $24, right around the average of $28 for similar pieces." `session["price_assessment"]` = "...".

**Step 4 — Outfit suggestion:**
`suggest_outfit(lst_006, example_wardrobe)` builds a prompt listing all 10 wardrobe items and asks the LLM for outfit combinations. LLM returns: "Pair this boxy bootleg tee with your baggy straight-leg jeans (dark wash) and chunky white sneakers for an easy, laid-back streetwear look — roll the sleeves once for shape. For something grungier, try it with your wide-leg khaki trousers and black combat boots, and layer the vintage black denim jacket over the top." `session["outfit_suggestion"]` = "...".

**Step 5 — Fit card:**
`create_fit_card(outfit_suggestion, lst_006)` sends the item details + outfit to the LLM with temperature=1.0. Returns: "thrifted this 2003 bootleg tee off depop for $24 and it just works with my dark jeans and chunky sneakers every time 🖤 the faded graphic is doing everything. full look in my stories." `session["fit_card"]` = "...".

**Final output to user:**
- Panel 1 (listing): "**Graphic Tee — 2003 Tour Bootleg Style** | $24.00 | depop | Size: L | Condition: good | Style: graphic tee, vintage, grunge, streetwear, band tee | 💰 Price check: This is a fair price..."
- Panel 2 (outfit): The 2-outfit suggestion naming specific wardrobe pieces.
- Panel 3 (fit card): The casual Instagram-style caption.

**Error path (no results):**
If the user typed "designer ballgown size XXS under $5", `search_listings` returns `[]`. `session["error"]` is set to "No listings found for 'designer ballgown' in size XXS under $5. Try broader keywords, removing the size filter, or increasing your budget." Panel 1 shows the error. Panels 2 and 3 are empty. `suggest_outfit` and `create_fit_card` are never called.

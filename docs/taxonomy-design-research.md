# Taxonomy Design & Information Architecture for Content Classification

## A Research Paper for Event Discovery Platforms

---

## 1. What Is This Discipline Called?

The process of organizing content into categories, subcategories, and tags sits at the intersection of several disciplines:

- **Information Architecture (IA)** — The structural design of shared information environments. Coined by Richard Saul Wurman (1989). Encompasses organization, labeling, navigation, and search systems.
- **Taxonomy Design** — Building controlled, hierarchical classification structures. Closer to library science, indexing, and knowledge management.
- **Ontology Design** — Goes beyond taxonomy by defining semantic relationships between concepts (e.g., "Surfing is-a Sport" but also "Surfing requires Ocean").
- **Knowledge Organization Systems (KOS)** — The academic umbrella for all structured ways of organizing knowledge.

**Key distinction:** IA is a design discipline (UX, psychology, sociology). Taxonomy is a tool/system within IA (indexing, NLP, knowledge management).

---

## 2. Foundational Frameworks

### LATCH Principle (Wurman)

All information can only be organized in five ways:

| Method | Example |
|--------|---------|
| **L**ocation | Map-based event discovery |
| **A**lphabet | A-Z venue directory |
| **T**ime | Calendar / timeline view |
| **C**ategory | Genre-based filtering (music, culture, food) |
| **H**ierarchy | Ranked by relevance / popularity |

### Rosenfeld & Morville's Four Systems

1. **Organization systems** — How content is grouped (schemes & structures)
2. **Labeling systems** — How content is named/represented
3. **Navigation systems** — How users browse and move through content
4. **Search systems** — How users query and retrieve content

### Faceted Classification (Ranganathan, 1930s)

Items are described along multiple independent dimensions (facets) simultaneously. For events:

- **Type:** Concert, Workshop, Exhibition, Market
- **Genre:** Jazz, Electronic, Classical
- **Setting:** Indoor, Outdoor
- **Price:** Free, Paid
- **Audience:** Family, 18+, All ages

This is now the backbone of modern filter UX on Airbnb, Spotify, Eventbrite, and e-commerce platforms.

---

## 3. Taxonomy vs. Folksonomy

| Dimension | Taxonomy | Folksonomy |
|-----------|----------|------------|
| Structure | Hierarchical, controlled | Flat, uncontrolled |
| Created by | Domain experts | End users |
| Language | Standardized | Natural, varied |
| Pros | Consistent, precise, navigable | Scalable, reflects user language |
| Cons | Expensive, may not match user mental models | Messy, inconsistent, synonym chaos |

**Best practice: Hybrid approach.** Allow users to suggest tags (folksonomy), then normalize them into a controlled vocabulary. This is exactly our challenge — our scrapers generate tags like `family-friendly`, `children`, `kids`, `kinderfreundlich` for the same concept.

---

## 4. Key Design Principles

### MECE (Mutually Exclusive, Collectively Exhaustive)

Each item should fit in exactly one primary category, and categories together should cover all content. Our current problem: a "Kinderkonzert" could be `music` or `family` — MECE is violated.

**Solution approaches:**
- **Primary category + audience tag** — Keep the event as `music` but tag it `audience:family`
- **Polyhierarchy** — Allow items to appear in multiple categories (Spotify does this)
- **Strict primary** — Force one category based on the dominant intent (our current approach)

### User-Centered Language

Labels should use vocabulary familiar to users, not internal jargon. Test labels with real users via card sorting.

### Balanced Depth & Breadth

- Too many top-level categories → overwhelming
- Too many levels deep → users get lost
- Rule of thumb: 5-9 top-level categories, 2-3 levels max

### Consistent Granularity

Categories at the same level should have similar specificity. Don't mix "Music" (broad) with "Jazz" (narrow) at the same level.

### Controlled Vocabulary

Solves:
- **Synonyms** — "kids" vs. "children" vs. "Kinder" → standardize to one
- **Homographs** — "bass" (fish) vs. "bass" (music)
- **Polysemy** — "family" (the audience) vs. "family-friendly" (an accessibility attribute)

---

## 5. How Major Platforms Handle This

### Airbnb — Knowledge Graph

- Built a universal hierarchical taxonomy stored as a graph database
- Designed to be MECE
- Uses **ML + human-in-the-loop** for classification
- High-level concepts map to specific activities
- Started with Experiences, expanded across all verticals
- 2022: Launched "Categories" (Lakefront, Countryside, Surfing, etc.)

*Source: [Airbnb Engineering Blog](https://medium.com/airbnb-engineering/contextualizing-airbnb-by-building-knowledge-graph-b7077e268d5a)*

### Spotify — Multi-Dimensional Classification

- Returns 5-6 **micro-genre tags** per track (not one genre)
- Uses 12 audio features as classification dimensions (danceability, energy, valence, etc.)
- **Hybrid human + algorithmic** — ML models + user playlist data as implicit folksonomy
- Powers Discover Weekly, Daily Mixes, Radio

### Eventbrite — Two-Facet System

- **Event Types** (format): Conference, Workshop, Festival
- **Event Topics** (subject): Music, Business, Food
- Organizers select from both lists — simple faceted system
- Auto-suggests categories for public events

### Netflix — Micro-Genre Taxonomy

- Thousands of hyper-specific categories: "Critically Acclaimed Emotional Dramas"
- Constructed algorithmically by combining tags: mood, plot type, setting, audience, critical reception
- Deep taxonomy invisible to users, powers recommendations

---

## 6. UX Research Methods

### Card Sorting

Users sort content items into groups and label those groups. Reveals mental models.

| Type | When to use |
|------|-------------|
| **Open** | Early — discover how users think about categories |
| **Closed** | Later — validate proposed categories |
| **Hybrid** | Use pre-defined categories but allow creating new ones |

**Tools:** OptimalSort, Maze, UserZoom

### Tree Testing

Validates whether a proposed navigation structure works. Users are given tasks ("Find a kids concert near Prenzlauer Berg") and navigate a text-only hierarchy.

Measures:
- **Findability** (success rate)
- **Directness** (straight path vs. backtracking)
- **Time to completion**

**Tools:** Treejack (Optimal Workshop), UserZoom

### Recommended Workflow

1. Open card sort → discover mental models
2. Draft taxonomy based on findings
3. Tree test → validate the draft
4. Iterate based on results
5. Repeat

---

## 7. Our Specific Challenge: Event Classification

### The Problem

Our pipeline tags events with uncontrolled vocabulary:
- `family-friendly` (attribute, not a category)
- `children` (audience)
- `kids` (synonym for children)
- `kinderfreundlich` (German synonym)
- `family-event` (subcategory)
- `kids-program` (subcategory)

A "Kinderkonzert" gets categorized as `music` with tag `children`. A puppet theater gets `culture` with tag `family-friendly`. Both are primarily family events but our taxonomy doesn't capture this.

### Root Cause

We conflate two dimensions:
1. **Content type** (what the event IS): concert, theater, market, exhibition
2. **Audience** (who it's FOR): families, adults, everyone

### Possible Solutions

**Option A: Audience as a separate facet**
```
category: music
subcategory: classical
audience: family
```
Events can be "music for families" without losing the music classification. Users who select "family" in onboarding see all events tagged `audience:family`, regardless of category.

**Option B: Primary category based on dominant intent (current approach)**
A Kinderkonzert → `family` / `kids-program`. Loses the "music" signal.

**Option C: Polyhierarchy (multiple categories)**
```
categories: [music, family]
subcategory: kids-program
```
Event appears in both feeds. More complex to implement but most accurate.

**Option D: Airbnb-style knowledge graph**
Model events as nodes with typed relationships:
```
Event --is_a--> Concert
Event --genre--> Classical
Event --audience--> Family
Event --setting--> Outdoor
```
Most flexible but heaviest to build.

### Recommendation

**Short-term:** Option A — Add an `audience` tag dimension. Keep content-type categories clean. Filter family feed by `audience:family` across all categories.

**Long-term:** Option C or D — Allow events to live in multiple categories, powered by a simple knowledge graph.

---

## 8. Essential Reading List

### Books (Priority Order)

1. **"Information Architecture: For the Web and Beyond"** (4th ed.) — Rosenfeld, Morville, Arango (2015) — *The canonical textbook*
2. **"Everyday Information Architecture"** — Lisa Maria Marquis (2019) — *Practical, accessible guide*
3. **"The Accidental Taxonomist"** (3rd ed.) — Heather Hedden (2022) — *The definitive taxonomy practice book*
4. **"How to Make Sense of Any Mess"** — Abby Covert (2014) — *Introductory, great for non-specialists*
5. **"Pervasive Information Architecture"** — Resmini & Rosati (2011) — *Cross-channel IA*

### Articles & Resources

- [Taxonomy 101 — NNGroup](https://www.nngroup.com/articles/taxonomy-101/)
- [Card Sorting vs. Tree Testing — NNGroup](https://www.nngroup.com/articles/card-sorting-tree-testing-differences/)
- [Filters vs. Facets — NNGroup](https://www.nngroup.com/articles/filters-vs-facets/)
- [Airbnb Knowledge Graph — Engineering Blog](https://medium.com/airbnb-engineering/contextualizing-airbnb-by-building-knowledge-graph-b7077e268d5a)
- [How to Develop a Taxonomy — Optimal Workshop](https://www.optimalworkshop.com/blog/how-to-develop-a-taxonomy-for-your-information-architecture)
- [Folksonomies and Taxonomies in UX — Maria Jennings](https://medium.com/@mariajennings/folksonomies-and-taxonomies-in-ux-design-4ba0071ba186)

### Communities

- **World IA Day** — Annual global event
- **IA Institute** — Professional organization
- **IA Conference** — Annual academic/professional conference

---

## 9. Key Takeaways

1. **Our tagging problem is a classic controlled vocabulary failure** — synonyms and mixed dimensions (content type vs. audience) create classification chaos.
2. **Faceted classification is the answer** — separate content type, genre, audience, and setting into independent dimensions.
3. **Card sorting with real users** would reveal whether "family" is a category (content type) or an audience filter in users' mental models.
4. **Hybrid tagging** (controlled vocabulary + user suggestions) scales better than pure taxonomy or pure folksonomy.
5. **Start simple, evolve** — Add an `audience` facet now, consider polyhierarchy or a knowledge graph later.

---

*Compiled March 2026 for the NachtKarte / Event-Map project.*

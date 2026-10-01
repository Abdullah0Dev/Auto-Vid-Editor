# Graphics Maker — Templates & Overlays Guide

A Remotion-based toolkit for Arabic history & Islamic content. Each template is a **self-contained scene** driven by a single `CONFIG` block at the top of its file. Change the config, get a new scene.

---

## The CONFIG convention

Every template follows the same shape:

```
remotion/src/templates/<name>.tsx
   │
   ├── ⚙️ CONFIG               ← one object, top of file
   │      content, timing, camera, layout, colors
   │
   ├── derived values          ← computed from CONFIG
   │
   ├── sub-components          ← WordSweep, Hemistich, etc.
   │
   └── MyAnimation             ← the composition
```

**Rules:**

1. All per-scene values live inside `CONFIG`. Nothing user-facing is hardcoded in the JSX.
2. Sub-components receive computed props; they never read CONFIG except for colors.
3. Derived values (`WORD_DURATION`, `needsScroll`, etc.) are computed **once, at module scope**, from CONFIG.
4. Colors are grouped under `CONFIG.colors`. Background image path is `CONFIG.colors.backgroundImg`.

**Why:** the Python pipeline can override any CONFIG field at render time via Remotion `--props` JSON — no source editing per scene.

---

## Quick reference

| # | Template | File | Category | Use it for |
|---|---|---|---|---|
| 1 | [Poem](#1-poem) | `poem.tsx` | Text | Classical Arabic poetry (شعر) |
| 2 | [Hadith](#2-hadith) | `hadith.tsx` | Text | Hadith with isnad + matn |
| 3 | [Quran](#3-quran) | `quran.tsx` | Text | Quran ayahs with ayah markers |
| 4 | [Quote](#4-quote) | `quote.tsx` | Text | Wise sayings (اقتباس) |
| 5 | [Battle](#5-battle) | `battle.tsx` | Event | Battles, wars, conquests |
| 6 | [Islamic Map](#6-islamic-map) | `map.tsx` | Geography | Travel routes, cities |
| 7 | [Audio Visualizer](#7-audio-visualizer) | `audio-visualizer.tsx` | Audio | VO or music with bars/waveform |
| 8 | [Person Card](#8-person-card) | `person-card.tsx` | Profile | Scholar, caliph, historical figure |
| 9 | [Ken Burns](#9-ken-burns) | `ken-burns.tsx` | Visual | Breathing room over a still image |
| 10 | [Counter](#10-counter) | `counter.tsx` | Data | Big number count-up for statistics |
| 11 | [Caption](#11-caption) | `caption.tsx` | Overlay | Word-by-word synced captions |

**Overlays** (attach to any template):
- [DateOverlay](#overlay-dateoverlay) — corner date marker

---

## Universal design system

Every template shares the same palette, fonts, and camera dolly. This is what makes all templates feel like one continuous video when chained.

### Palette

| Hex | Name | Usage |
|---|---|---|
| `#0B3D2E` | أخضر زمردي | Primary bg, Islamic identity |
| `#0F1B2D` | كحلي تاريخي | Night bg, gravity, depth |
| `#C9A227` | ذهبي عتيق | Titles, borders, gold accents |
| `#F2E8D5` | بيج بردي | Text, parchment backgrounds |
| `#5A3E2B` | بني جلدي | Frames, manuscripts |
| `#7A1F2B` | عنابي | Battles, bloody events |
| `#3F4A4A` | رمادي حجري | Wars, maps, cold scenes |
| `#FAF7F0` | أبيض عاجي | Primary clear text |
| `#B87333` | نحاسي | Al-Andalus, warm detail |

### Common CONFIG blocks

Every template exposes at least these three:

```ts
camera: {
  startFrame: 10,      // when dolly-in begins
  endFrame: 55,        // when it stops
  scale: 1.13,         // zoom amount
  rotateX: 12,         // 3D tilt (degrees)
}

colors: {
  text:          "rgba(217, 196, 122, 0.7)",
  accent:        "#b8935a",
  dim:           "#8a6f3c",
  highlightRgb:  "217, 170, 60",       // rgb triplets for gradients
  background:    "#0a2e1c",
  backgroundImg: "poem-bg.jpeg",       // path under remotion/public/
}

fps: 30
```

### Common files

- **Background:** `remotion/public/poem-bg.jpeg` (all templates use this by default)
- **Font:** `remotion/public/fonts/Tajawal-Medium.ttf`
- **Output size:** 1920 × 1080 @ 30fps

---

## 1. Poem

**File:** `remotion/src/templates/poem.tsx`
**Category:** Text
**Use for:** classical Arabic poetry with a hemistich-based sweep.

### What it does
- Splits each بيت into two شطر (hemistichs) side by side
- Sweeps a gold highlight across each شطر in reading order (right → left)
- Auto-scrolls if the poem is longer than `visibleRows`
- Camera dolly-in for the first ~2s

### Key config

| Setting | What it changes |
|---|---|
| `CONFIG.poemLines` | Array of `{ text1, text2 }` — each object is one بيت |
| `CONFIG.footerLabel` | Attribution below the poem |
| `CONFIG.totalReadingSeconds` | Total recitation length — auto-distributes across شطر |
| `CONFIG.highlightStart` / `.highlightGap` | When the first sweep starts, and the pause between شطر |
| `CONFIG.defaultHighlightDuration` | Fallback duration when `totalReadingSeconds` is `null` |
| `CONFIG.visibleRows` | Rows visible before scroll kicks in |
| `CONFIG.scrollAnchorRow` | Which row holds the "current" position while scrolling |
| `CONFIG.fontSize` / `.lineHeight` / `.lineGap` | Typography |
| `CONFIG.hemistichWidth` | Fixed width per شطر — keeps edges aligned |
| `CONFIG.contentPadding` | Left/right padding of the poem block |
| `CONFIG.camera` | `{ startFrame, endFrame, scale, rotateX }` |
| `CONFIG.colors.*` | All colors incl. `backgroundImg` |

### When to use
- Poetry recitation (شعر)
- Rhymed prose with structured lines
- Anything where two halves of a line need aligned edges

---

## 2. Hadith

**File:** `remotion/src/templates/hadith.tsx`
**Category:** Text
**Use for:** Hadith with an isnad line and a matn body.

### What it does
- Isnad (chain of narration) at top — single line, single sweep
- Matn (the saying) below — split into words, each sweeps in sequence
- Words flow inline as one justified paragraph, wrapping naturally
- Auto-scrolls if content is longer than the viewport
- Auto-wraps the matn in `«…»` (no need to type them)

### Key config

| Setting | What it changes |
|---|---|
| `CONFIG.topLabel` | Top decorative label (default `حَـدِيـث`) |
| `CONFIG.isnad` | Chain of narration — single line sweep |
| `CONFIG.matnPlain` | The matn (body) — plain text, no `«»` needed |
| `CONFIG.source` | Footer attribution (رواه...) |
| `CONFIG.totalReadingSeconds` | Total recitation length |
| `CONFIG.isnadDuration` | Frames the isnad takes to sweep |
| `CONFIG.isnadFontSize` / `.fontSize` / `.lineHeight` | Typography |
| `CONFIG.textBlockWidth` | Width of the text block (default `"70%"`) |
| `CONFIG.viewportLines` | Max visible lines before auto-scroll |
| `CONFIG.charsPerLineEstimate` | Estimation knob for the scroll math |
| `CONFIG.camera` | Dolly settings |
| `CONFIG.colors.*` | Palette |

### When to use
- Hadith narration
- Any text with a narrator preface + main body
- Legal rulings, scholarly sayings

---

## 3. Quran

**File:** `remotion/src/templates/quran.tsx`
**Category:** Text
**Use for:** Quran ayahs with proper Mushaf layout.

### What it does
- Basmala header (static)
- Verses flow as one continuous paragraph (like a Mushaf page)
- Inline ayah markers (۝١ ۝٢ ۝٣) with Eastern Arabic numerals
- Per-verse sweep — one highlight per ayah
- Auto-scrolls if the surah is long

### Key config

| Setting | What it changes |
|---|---|
| `CONFIG.basmala` | Header text (default بِسْمِ اللَّهِ…) |
| `CONFIG.surahName` | Footer surah name |
| `CONFIG.verses` | Array of `{ text, number }` — `number` drives the ۝ marker |
| `CONFIG.totalReadingSeconds` | Full recitation length |
| `CONFIG.highlightStart` / `.highlightGap` | When the first sweep starts, gap between ayahs |
| `CONFIG.defaultHighlightDuration` | Fallback when `totalReadingSeconds` is `null` |
| `CONFIG.fontSize` / `.lineHeight` | Typography |
| `CONFIG.textBlockWidth` | Text width (default `"70%"`) |
| `CONFIG.viewportLines` | Max visible lines before auto-scroll |
| `CONFIG.charsPerLineEstimate` | Estimation knob for scroll math |
| `CONFIG.camera` | Dolly settings |
| `CONFIG.colors.*` | Palette (`textReading` is the "currently reading" shade) |

### When to use
- Quran recitation (سورة كاملة or جزء)
- Any passage with verse markers

---

## 4. Quote

**File:** `remotion/src/templates/quote.tsx`
**Category:** Text
**Use for:** Wise sayings (اقتباس).

### What it does
- Speaker line at top — single sweep
- Quote body — split into words, each sweeps in sequence
- Auto-wraps the quote in `«…»` (no need to type them)
- Footer attribution

### Key config

| Setting | What it changes |
|---|---|
| `CONFIG.topLabel` | Top decorative label (default `اقْـتِـبَـاس`) |
| `CONFIG.speaker` | Speaker line (e.g. `قَالَ ابْنُ الْقَيِّمِ`) |
| `CONFIG.quotePlain` | The quote — plain text, no `«»` needed |
| `CONFIG.source` | Footer attribution |
| `CONFIG.totalReadingSeconds` | Total reading length |
| `CONFIG.speakerDuration` | Frames the speaker line takes to sweep |
| `CONFIG.speakerFontSize` / `.fontSize` / `.lineHeight` | Typography |
| `CONFIG.textBlockWidth` | Width of the text block (default `"70%"`) |
| `CONFIG.viewportLines` | Max visible lines before auto-scroll |
| `CONFIG.quoteCharsPerLine` | Estimation knob for scroll math |
| `CONFIG.camera` | Dolly settings |
| `CONFIG.colors.*` | Palette |

> **Note:** Quote and Hadith share the same underlying CONFIG shape. The pipeline treats them interchangeably — pick whichever fits the content.

### When to use
- Quotes from scholars, leaders, historical figures
- Brief wisdoms (حِكَم)
- Short passages with attribution

---

## 5. Battle

**File:** `remotion/src/templates/battle.tsx`
**Category:** Event
**Use for:** Battles, wars, conquests.

### What it does
- Dual-calendar date at top (هـ + م)
- Battle name with a hero sweep
- Two contending sides with names + leaders
- Crossed-swords emblem between them
- Outcome line
- Source footer

### Key config

| Setting | What it changes |
|---|---|
| `hijriDate` / `miladiDate` | Dual-calendar date |
| `battleName` | Hero text (gets the sweep) |
| `side1` / `side2` | Contending factions — `{ name, detail }` |
| `outcome` | Result line |
| `source` | Reference |
| `camera` / `colors.backgroundImg` | Same convention as all templates |

### When to use
- Major battles (بدر، اليرموك، حطين)
- Conquests (فتح الأندلس، فتح القسطنطينية)
- Wars and campaigns

---

## 6. Islamic Map

**File:** `remotion/src/templates/map.tsx`
**Category:** Geography
**Use for:** Cities, journeys, territorial extents.

### What it does
- All cities appear simultaneously as glowing pins
- Optional **spotlight** on a single city (pulsing gold ring + label)
- Optional **journey** — draws a gold line connecting cities in order
- Icons: Kaaba, mosque, star, city, battle

### Key config

| Setting | What it changes |
|---|---|
| `spotlight` | `{ cityId, startFrame, label }` or `null` | like this person where here or whatever..
| `journey` | `{ path: ["id1","id2"], startFrame, drawDuration, color, label }` or `null` |
| `title` / `subtitle` / `footer` | Text overlays |
| `camera` / `mapImage` | Dolly + map background |

### Icons available
`"kaaba"` · `"mosque"` · `"star"` · `"city"` · `"battle"`

### When to use
- Travel narratives (رحلة ابن بطوطة)
- Conquests spreading across regions
- Locating a story geographically

---

## 7. Audio Visualizer

**File:** `remotion/src/templates/audio-visualizer.tsx`
**Category:** Audio
**Use for:** Voiceover or music with real-time bars/waveform.

### What it does
- Two modes: **spectrum** (mirrored bars) or **waveform** (flowing line)
- Bass-reactive ambient glow behind the visualizer
- Optional speaker + subtitle header
- Audio playback via `<Audio>` from `@remotion/media`

### Key config

| Setting | What it changes |
|---|---|
| `audioSrc` | Path to audio file (default `audio/test.wav`) |
| `mode` | `"spectrum"` or `"waveform"` |
| `spectrum.barCount` | 32 / 64 / 128 / 256 / 512 bars |
| `spectrum.mirror` | `true` mirrors around center, `false` single-sided |
| `spectrum.maxHeight` | Peak bar height in px |
| `waveform.windowInSeconds` | History shown (0.25 short, 1.0 long) |
| `title` | `{ speaker, subtitle }` or `null` |
| `bassGlow` | `{ enabled, maxOpacity, intensityMultiplier }` |

### When to use
- Recitation with on-screen visual reaction
- Music bed segments
- Podcast / lecture moments

---

## 8. Person Card

**File:** `remotion/src/templates/person-card.tsx`
**Category:** Profile
**Use for:** Introducing a scholar, caliph, or historical figure.

### What it does
- Portrait (left) with gold frame + corner ornaments
- Name (right) — word-by-word sweep
- Honorific (`رحمه الله`, `ﷺ`, `رضي الله عنه`) styled distinctly
- Title / laqab line
- Birth–death dates (Hijri)
- Birthplace → deathplace
- Optional footer label

### Key config

| Setting | What it changes |
|---|---|
| `portraitSrc` | Image path, or `null` for monogram fallback |
| `name` | Full name — gets the sweep |
| `honorific` | `رحمه الله` / `رضي الله عنه` etc. |
| `title` | Laqab (e.g. `المحدث الأعظم`) |
| `birthYear` / `deathYear` | Hijri years (default) |
| `birthPlace` / `deathPlace` | Cities |
| `footerLabel` | Series name or book title |

### When to use
- Introducing any historical figure
- Transitions between scholars in a lecture
- Biography segments

---

## 9. Ken Burns

**File:** `remotion/src/templates/ken-burns.tsx`
**Category:** Visual
**Use for:** Breathing room over a still image (paintings, maps, manuscripts).

### What it does
- Slow zoom + pan over the image
- Optional caption at the bottom
- Camera dolly layered on top
- Same palette tint and vignette as all templates

### Key config

| Setting | What it changes |
|---|---|
| `imageSrc` | Image path |
| `motion` | `"zoom-in"` `"zoom-out"` `"pan-left"` `"pan-right"` `"pan-up"` `"pan-down"` `"diagonal-tl/tr/bl/br"` |
| `startScale` / `endScale` | Zoom range (1.0 → 1.18 default) |
| `panAmount` | Pan distance (% of image size) |
| `caption` | `{ line1, line2? }` or `null` |
| `source` | Small footnote above the caption |

### When to use
- Descriptive VO over a historical image
- **Rule:** every 20–30 seconds of video should have one
- Transitions between information-dense scenes

---

## 10. Counter

**File:** `remotion/src/templates/counter.tsx`
**Category:** Data
**Use for:** Making a single number land emotionally.

### What it does
- Big number counts up from 0 to target
- Ambient gold glow that peaks mid-count
- Completion "bump" (scale punch) when it hits the target
- Top label + main label + sub-label
- Arabic or Western numerals

### Key config

| Setting | What it changes |
|---|---|
| `value` | The number to count to |
| `prefix` / `suffix` | Text around the number (`+`, `كم`, `سنة`) |
| `numberFormat` | `"arabic"` (٩٠٠) or `"western"` (900) |
| `thousandsSeparator` | `"٬"` `","` or `""` |
| `label` | Main label below the number |
| `subLabel` | Smaller secondary text |
| `topLabel` | Decorative label above (or `null`) |
| `curve` | `"linear"` `"easeOut"` `"easeInOut"` |
| `countDuration` | How long the count takes (frames) |

### When to use
- Statistics (`٩٠٠٬٠٠٠ حديث`)
- Distances, casualties, populations
- "How many" or "how long" beats

---

## 11. Caption

**File:** `remotion/src/templates/caption.tsx`
**Category:** Overlay
**Use for:** Word-by-word synced captions on top of any scene.

### What it does
- Words light up one-by-one as spoken
- Multiple animation styles to choose from
- Multiple color themes matching the palette
- Can work standalone or layered on top of any other template

### Key config

| Setting | What it changes |
|---|---|
| `style` | Animation style (underline / rise / pop / blurFocus / dualTone / wave) |
| `theme` | Color theme (parchment / crimson / andalusian / night) |
| `text` | Plain Arabic — will be split into words |
| `timing` | `"auto"` (distribute evenly) or `"manual"` (use timestamps) |
| `readingSeconds` | Total length (auto mode) |
| `manualTimestamps` | Array of word start times in seconds (manual mode) |
| `activeDurationSeconds` | How long a word stays lit |
| `fontSize` | Caption text size |
| `header` | Top label (optional) |
| `bottomPercent` | Vertical position |

### When to use
- Any scene with Arabic VO
- Makes content watchable on mute
- Word-level sync feels professional

---

## Overlay: DateOverlay

**File:** `remotion/src/templates/overlays/date.tsx`

### What it does
- Corner pill showing current Hijri + Gregorian date
- Updates as the timeline advances — slides + fades on each change
- Subtle gold pulse when a date changes
- Optional label below the pill

### Props

```tsx
<DateOverlay
  events={[
    { from: 0,   hijri: "١٤٥هـ", miladi: "٧٦٢م", label: "تَأْسِيسُ بَغْدَاد" },
    { from: 120, hijri: "٣٥٨هـ", miladi: "٩٦٩م", label: "تَأْسِيسُ القَاهِرَة" },
  ]}
  position="top-right"       // "top-right" | "top-left" | "bottom-right" | "bottom-left"
  transitionFrames={18}      // default 18 (0.6s)
/>
```

| Prop | Type | Purpose |
|---|---|---|
| `events` | array | Each `{ from, hijri, miladi?, label? }` — `from` is the frame when it becomes active |
| `position` | string | Which corner |
| `transitionFrames` | number | Slide/fade duration per change |

### How to use it

Just `import { DateOverlay } from "./overlays/date"` inside any template and render it wherever you want — the same as any other React component.

### When to use
- Any scene where the timeline matters
- On chapter transitions ("we're now in 762 CE")
- To anchor a story that jumps through history

---

## Driving templates from Python (props override)

The Python pipeline never edits template source files. Instead, it sends per-scene props as JSON to Remotion's CLI:

```bash
npx remotion render src/index.ts hadith out.mp4 \
  --props='{"isnad":"...","matnPlain":"...","totalReadingSeconds":22}'
```

The template merges incoming props over its `CONFIG` defaults. Rules:

- **Prop keys match CONFIG keys exactly.** `totalReadingSeconds` overrides `CONFIG.totalReadingSeconds`.
- **Nested objects merge one level deep.** Passing `{camera: {scale: 1.25}}` keeps `camera.startFrame` and friends intact.
- **`null` is respected.** Passing `totalReadingSeconds: null` uses `defaultHighlightDuration` instead.
- **Arrays replace wholesale.** Sending `verses: [...]` replaces the default list entirely.
- **Unknown keys are ignored.** Sending a typo like `isnadLine` does nothing; the default `isnad` stays.

### How the pipeline picks a template

`pipeline/graphic_planner.py` looks at the scene content and returns one of:

```
islamic_map    → for geography, journeys, spread of Islam
poem           → when the narrator quotes poetry
hadith         → sayings of the Prophet ﷺ
quote          → wisdom from scholars / figures
quran          → Quranic recitation
```

For text templates, the LLM is told to **keep the source Arabic faithful** —
it copies the transcript into `isnad` / `matnPlain` / `verses` / `poemLines`,
it doesn't paraphrase. Any field it isn't confident about is left out and
the template default takes over.

---

## How to use these together

### Typical video sequence

```
Chapter card   →  Ken Burns (opening mood)
   ↓
Person card    →  Map (journey)  →  Battle scene
   ↓
Quote / Hadith / Quran scene
   ↓
Counter (statistic)  →  Ken Burns (closer)  →  End card
```

Add `Caption` to any scene that has VO.
Add `DateOverlay` to every scene to keep the timeline anchored.

---

## Adding a new template

1. Create `remotion/src/templates/<name>.tsx`.
2. Drop a `CONFIG` object at the top (copy the shape from an existing template).
3. Export `MyAnimation`.
4. Register a `<Composition>` in `remotion/src/Root.tsx`:

   ```tsx
   <Composition
     id="<name>"
     component={MyAnimation}
     durationInFrames={300}
     fps={30}
     width={1920}
     height={1080}
   />
   ```
5. If the pipeline should be able to pick it, add the id to `_ALLOWED_TEMPLATES` in `pipeline/graphic_planner.py` and add a line describing when to use it in the planner's system prompt.

That's it — no registry file to update, no gallery, no compiler injection.

---

## File structure

```
remotion/
  package.json
  tsconfig.json
  src/
    index.ts                   ← Remotion entry (registerRoot)
    Root.tsx                   ← Compositions for every template
    templates/
      poem.tsx
      hadith.tsx
      quran.tsx
      quote.tsx
      battle.tsx
      islamic-map.tsx
      audio-visualizer.tsx
      person-card.tsx
      ken-burns.tsx
      counter.tsx
      caption.tsx
      overlays/
        date.tsx
  public/
    poem-bg.jpeg               ← shared background
    map-bg.jpg                 ← map template background
    fonts/Tajawal-Medium.ttf   ← shared font
    audio/test.wav             ← audio for the visualizer
```

---

## Quick decision: which template?

| You want to show... | Use |
|---|---|
| Poetry | **Poem** |
| A saying of the Prophet ﷺ | **Hadith** |
| Quran verses | **Quran** |
| A scholar's wisdom | **Quote** |
| A fight or campaign | **Battle** |
| Where something happened | **Islamic Map** |
| A VO or music without visuals | **Audio Visualizer** |
| Who someone was | **Person Card** |
| An image you want to linger on | **Ken Burns** |
| A big number | **Counter** |
| On-screen captions | **Caption** |
| What year we're in | **DateOverlay** (overlay on any) |

---

## Universal tuning

These apply to **every template** and are all driven through `CONFIG`:

**Camera intensity** — quieter or more dramatic:
```ts
CONFIG.camera = { startFrame: 10, endFrame: 55, scale: 1.08, rotateX: 6 }   // subtle
CONFIG.camera = { startFrame: 10, endFrame: 55, scale: 1.25, rotateX: 18 }  // dramatic
```

**Palette** — swap the whole color scheme by editing `CONFIG.colors`. Every
template reads from the same four core keys: `text`, `accent`, `dim`,
`highlightRgb`, plus `background` and `backgroundImg`.

**Font** — replace `public/fonts/Tajawal-Medium.ttf` or override `fontFamily`
via props.

**Duration** — for text templates, adjust `CONFIG.totalReadingSeconds`; for
audio-driven templates, use `calculateMetadata` in `Root.tsx` to auto-size
from the audio file.

**Background** — replace `CONFIG.colors.backgroundImg` with any image under
`public/`. All templates tint it toward the palette, so any reasonably dark
image works.

---

## Rendering

### Standalone (dev)
```bash
cd remotion
npx remotion studio src/index.ts
```

### CLI
```bash
cd remotion
npx remotion render src/index.ts <CompositionId> out/video.mp4
```

### From the Python pipeline
`pipeline/graphic_renderer.py` calls the CLI with props as JSON:

```bash
npx remotion render <bundle> <template-id> out.mp4 --props=/path/to/props.json
```

Results are cached by a hash of `(template, props, duration, transparent)`, so
re-rendering an unchanged scene is instantaneous.

---

## TL;DR

- **11 templates** + **1 overlay**, all sharing the same design language
- **Every template is CONFIG-driven** — edit one object at the top of the file
- **The Python pipeline can override any CONFIG field** via `--props` JSON
- **Text templates** (poem, hadith, quran, quote) are built for on-screen Arabic with per-word / per-verse sweeps
- **Pick a template based on the content type** (see the decision table)
- **Chain them** in a video: chapter → visual → people → story → numbers → close
- **Adding a new template** = one file + one `<Composition>` in `Root.tsx`
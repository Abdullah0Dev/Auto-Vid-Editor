import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  interpolate,
} from "remotion";
import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

// =============================================================================
// ⚙️ CONFIG — edit this block, that's it
// =============================================================================
const CONFIG = {
  // ── Content ────────────────────────────────────────────
  basmala:   "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
  surahName: "سورة الشرح",
  verses: [
    { text: "أَلَمْ نَشْرَحْ لَكَ صَدْرَكَ",        number: 1 },
    { text: "وَوَضَعْنَا عَنكَ وِزْرَكَ",          number: 2 },
    { text: "الَّذِي أَنقَضَ ظَهْرَكَ",            number: 3 },
    { text: "وَرَفَعْنَا لَكَ ذِكْرَكَ",           number: 4 },
    { text: "فَإِنَّ مَعَ الْعُسْرِ يُسْرًا",       number: 5 },
    { text: "إِنَّ مَعَ الْعُسْرِ يُسْرًا",        number: 6 },
    { text: "فَإِذَا فَرَغْتَ فَانصَبْ",            number: 7 },
    { text: "وَإِلَىٰ رَبِّكَ فَارْغَبْ",           number: 8 },
  ] as { text: string; number: number }[],

  // ── Timing ─────────────────────────────────────────────
  fps: 30,
  totalReadingSeconds: 30 as number | null,
  highlightStart: 70,
  highlightGap: 14,
  defaultHighlightDuration: 126.819,

  // ── Camera ─────────────────────────────────────────────
  camera: { startFrame: 10, endFrame: 55, scale: 1.13, rotateX: 15 },

  // ── Layout ─────────────────────────────────────────────
  fontSize: 46,
  lineHeight: 2.3,
  textBlockWidth: "70%",
  basmalaMarginBottom: 50,
  footerMarginTop: 60,
  viewportLines: 6,
  charsPerLineEstimate: 45,
  scrollStartFraction: 0.25,

  // ── Colors ─────────────────────────────────────────────
  colors: {
    text:          "rgba(217, 196, 122, 0.7)",
    textReading:   "#f5e5a8",
    accent:        "#b8935a",
    dim:           "#8a6f3c",
    highlightRgb:  "217, 170, 60",
    background:    "#0a2e1c",
    backgroundImg: "poem-bg.jpeg",
  },
};

// =============================================================================
// Derived values
// =============================================================================
const NUM_VERSES = CONFIG.verses.length;

const HIGHLIGHT_DURATION =
  CONFIG.totalReadingSeconds !== null && CONFIG.totalReadingSeconds > 0
    ? Math.max(
        10,
        (CONFIG.totalReadingSeconds * CONFIG.fps -
          CONFIG.highlightStart -
          (NUM_VERSES - 1) * CONFIG.highlightGap) /
          NUM_VERSES,
      )
    : CONFIG.defaultHighlightDuration;
const PER_VERSE = HIGHLIGHT_DURATION + CONFIG.highlightGap;

// Auto-scroll math
const totalChars = CONFIG.verses.reduce((s, v) => s + v.text.length + 4, 0);
const estimatedLines = Math.max(1, Math.ceil(totalChars / CONFIG.charsPerLineEstimate));
const LINE_PX = CONFIG.fontSize * CONFIG.lineHeight;
const estimatedContentHeight = estimatedLines * LINE_PX;
const VIEWPORT_HEIGHT_PX = CONFIG.viewportLines * LINE_PX;
const needsScroll = estimatedContentHeight > VIEWPORT_HEIGHT_PX + 5;
const maxScrollPx = Math.max(0, estimatedContentHeight - VIEWPORT_HEIGHT_PX);

// ── Arabic numerals ───────────────────────────────────────
const ARABIC_DIGITS = ["٠","١","٢","٣","٤","٥","٦","٧","٨","٩"];
const toArabicNumeral = (n: number): string =>
  String(n).split("").map((d) => ARABIC_DIGITS[Number(d)]).join("");

// =============================================================================
// Inline ayah marker
// =============================================================================
const AyahMarkerInline = ({ number }: { number: number }) => (
  <span style={{
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    width: "1.6em", height: "1.6em", borderRadius: "50%",
    border: `1.5px solid ${CONFIG.colors.accent}`,
    fontSize: "0.65em", lineHeight: 1, verticalAlign: "middle",
    color: CONFIG.colors.text,
    margin: "0 0.4em 0 0.15em",
    backgroundColor: "transparent", position: "relative",
  }}>
    {toArabicNumeral(number)}
  </span>
);

// =============================================================================
// One verse with the sweeping highlight
// =============================================================================
const Verse = ({
  text, number, delay,
}: { text: string; number: number; delay: number }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(
    frame - delay, [0, HIGHLIGHT_DURATION], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const bgImage = `linear-gradient(to left, rgba(${CONFIG.colors.highlightRgb}, 0.55) 50%, transparent 50%)`;
  return (
    <span style={{
      display: "inline",
      backgroundImage: bgImage,
      backgroundSize: "200% 100%",
      backgroundPosition: `${progress * 100}% 0`,
      backgroundRepeat: "no-repeat",
      boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone",
      padding: "0.05em 0.15em", borderRadius: 4,
      color: CONFIG.colors.text,
    }}>
      {text}{" "}<AyahMarkerInline number={number} />{" "}
    </span>
  );
};

// =============================================================================
// Main
// =============================================================================
export const MyAnimation = () => {
  const frame = useCurrentFrame();
  const [handle] = useState(() => delayRender("Loading Tajawal font"));
  useEffect(() => {
    const font = new FontFace("Tajawal", `url(${staticFile("fonts/Tajawal-Medium.ttf")})`);
    font.load()
      .then(() => { document.fonts.add(font); continueRender(handle); })
      .catch((err) => { console.error("Font load failed", err); continueRender(handle); });
  }, [handle]);

  const cameraScale = interpolate(
    frame, [CONFIG.camera.startFrame, CONFIG.camera.endFrame],
    [1, CONFIG.camera.scale],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const cameraRotateX = interpolate(
    frame, [CONFIG.camera.startFrame, CONFIG.camera.endFrame],
    [0, CONFIG.camera.rotateX],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const totalReadingFrames = (NUM_VERSES - 1) * PER_VERSE + HIGHLIGHT_DURATION;
  const elapsed = Math.max(0, frame - CONFIG.highlightStart);
  const readingProgress = Math.min(1, elapsed / totalReadingFrames);
  const scrollProgress = needsScroll
    ? Math.max(0, Math.min(1,
        (readingProgress - CONFIG.scrollStartFraction) /
        (1 - CONFIG.scrollStartFraction)))
    : 0;
  const scrollY = -scrollProgress * maxScrollPx;

  const versesContent = (
    <>
      {CONFIG.verses.map((v, i) => (
        <Verse
          key={i}
          text={v.text}
          number={v.number}
          delay={CONFIG.highlightStart + i * PER_VERSE}
        />
      ))}
    </>
  );

  return (
    <AbsoluteFill style={{
      backgroundColor: CONFIG.colors.background,
      overflow: "hidden", perspective: 1800, perspectiveOrigin: "center center",
    }}>
      <div style={{
        position: "absolute", inset: 0,
        transform: `scale(${cameraScale}) rotateX(${cameraRotateX}deg)`,
        transformOrigin: "center center", transformStyle: "preserve-3d",
      }}>
        <Img
          src={staticFile(CONFIG.colors.backgroundImg)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        />

        <AbsoluteFill style={{
          direction: "rtl",
          fontFamily: "'Tajawal', 'Noto Naskh Arabic', 'Amiri', serif",
          color: CONFIG.colors.text,
          display: "flex", flexDirection: "column",
          justifyContent: "center", alignItems: "center",
        }}>
          <div style={{
            fontSize: CONFIG.fontSize * 0.95,
            color: CONFIG.colors.accent,
            marginBottom: CONFIG.basmalaMarginBottom,
            opacity: 0.9,
          }}>
            {CONFIG.basmala}
          </div>

          <div style={{
            width: CONFIG.textBlockWidth,
            fontSize: CONFIG.fontSize,
            lineHeight: CONFIG.lineHeight,
            textAlign: "justify", textAlignLast: "right",
            wordSpacing: "0.05em",
            ...(needsScroll ? { height: VIEWPORT_HEIGHT_PX, overflow: "hidden", position: "relative" } : {}),
          }}>
            <div style={needsScroll
              ? { transform: `translateY(${scrollY}px)`, willChange: "transform" }
              : undefined}>
              {versesContent}
            </div>
          </div>

          <div style={{ marginTop: CONFIG.footerMarginTop, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <div style={{
              position: "relative", width: 520, height: 1,
              background: `linear-gradient(to right, transparent 0%, ${CONFIG.colors.dim} 25%, ${CONFIG.colors.dim} 75%, transparent 100%)`,
              marginBottom: 24,
            }}>
              <div style={{
                position: "absolute", top: -5, left: "50%",
                transform: "translateX(-50%) rotate(45deg)",
                width: 10, height: 10, backgroundColor: CONFIG.colors.text,
              }} />
            </div>
            <div style={{ fontSize: 30, color: CONFIG.colors.text, opacity: 0.9 }}>
              {CONFIG.surahName}
            </div>
          </div>
        </AbsoluteFill>
      </div>
    </AbsoluteFill>
  );
};

// ─── Public type — the LLM/pipeline sees this ─────────────
export type quranProps = Partial<typeof CONFIG> & {
  camera?: Partial<typeof CONFIG.camera>;
  colors?: Partial<typeof CONFIG.colors>;
};

export const quranDefaults = CONFIG;
export const Quran = MyAnimation;
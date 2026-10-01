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
// ⚙️ CONFIG — default values
// =============================================================================
const CONFIG = {
  // ── Content ────────────────────────────────────────────
  topLabel: "اقْـتِـبَـاس",
  speaker: "قَالَ ابْنُ الْقَيِّمِ رَحِمَهُ اللَّهُ:",
  quotePlain: `الإنصاف في معاملة الله: أن يعطى العبودية حقها وأن لا ينازع ربه صفات إلهيته التي لا تليق بالعبد ولا تنبغي له: من العظمة والكبرياء والجبروت ومن إنصافه لربه: أن لا يشكر سواه على نعمه وينساه ولا يستعين بها على معاصيه ولا يحمد على رزقه غيره ولا يعبد سواه`,
  source: "ابْنُ الْقَيِّمِ الْجَوْزِيَّة",

  // ── Timing ─────────────────────────────────────────────
  fps: 30,
  totalReadingSeconds: 18 as number | null,
  highlightStart: 70,
  speakerDuration: 55,

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 55,
    scale: 1.13,
    rotateX: 15,
  },

  // ── Layout ─────────────────────────────────────────────
  fontSize: 46,
  speakerFontSize: 36,
  lineHeight: 2.2,
  textBlockWidth: "70%",
  topDecorMarginBottom: 50,
  speakerMarginBottom: 40,
  footerMarginTop: 70,
  quoteCharsPerLine: 48,
  viewportLines: 6,
  scrollStartFraction: 0.25,

  // ── Colors ─────────────────────────────────────────────
  colors: {
    text: "rgba(217, 196, 122, 0.7)",
    accent: "#b8935a",
    dim: "#8a6f3c",
    highlightRgb: "217, 170, 60",
    background: "#0a2e1c",
    backgroundImg: "poem-bg.jpeg",
  },
};

// =============================================================================
// Public props
// =============================================================================
export type quoteProps = Partial<typeof CONFIG> & {
  durationInFrames?: number;

  camera?: Partial<typeof CONFIG.camera>;
  colors?: Partial<typeof CONFIG.colors>;
};

// =============================================================================
// Helpers
// =============================================================================

const normalizeQuote = (text: string): string => {
  const trimmed = text.trim();
  const stripped = trimmed.replace(/^«\s*|\s*»$/g, "").trim();
  return `«${stripped}»`;
};

// =============================================================================
// Word sweep
// =============================================================================

const WordSweep = ({
  text,
  delay,
  duration,
  highlightRgb,
  textColor,
}: {
  text: string;
  delay: number;
  duration: number;
  highlightRgb: string;
  textColor: string;
}) => {
  const frame = useCurrentFrame();

  const progress = interpolate(
    frame - delay,
    [0, duration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const bgImage = `linear-gradient(
    to left,
    rgba(${highlightRgb}, 0.55) 0%,
    rgba(${highlightRgb}, 0.55) ${progress * 100}%,
    transparent ${progress * 100}%,
    transparent 100%
  )`;

  return (
    <span
      style={{
        display: "inline",
        backgroundImage: bgImage,
        backgroundRepeat: "no-repeat",
        boxDecorationBreak: "clone",
        WebkitBoxDecorationBreak: "clone",
        color: textColor,
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// Speaker sweep
// =============================================================================

const SpeakerSweep = ({
  text,
  delay,
  duration,
  highlightRgb,
  textColor,
}: {
  text: string;
  delay: number;
  duration: number;
  highlightRgb: string;
  textColor: string;
}) => {
  const frame = useCurrentFrame();

  const progress = interpolate(
    frame - delay,
    [0, duration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const bgImage = `linear-gradient(
    to left,
    rgba(${highlightRgb}, 0.55) 0%,
    rgba(${highlightRgb}, 0.55) ${progress * 100}%,
    transparent ${progress * 100}%,
    transparent 100%
  )`;

  return (
    <span
      style={{
        display: "inline",
        backgroundImage: bgImage,
        backgroundRepeat: "no-repeat",
        boxDecorationBreak: "clone",
        WebkitBoxDecorationBreak: "clone",
        color: textColor,
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<quoteProps> = (props) => {
  // ── Merge defaults + runtime props ──────────────────────
  const config = {
    ...CONFIG,
    ...props,

    camera: {
      ...CONFIG.camera,
      ...(props.camera ?? {}),
    },

    colors: {
      ...CONFIG.colors,
      ...(props.colors ?? {}),
    },
  };

  const frame = useCurrentFrame();

  // ── Runtime duration ───────────────────────────────────
  // The Python pipeline sends durationInFrames.
  // When totalReadingSeconds was not explicitly supplied,
  // derive it from the actual render duration.
  const runtimeTotalReadingSeconds =
    props.totalReadingSeconds != null
      ? props.totalReadingSeconds
      : typeof props.durationInFrames === "number" &&
          props.durationInFrames > 0
        ? props.durationInFrames / config.fps
        : config.totalReadingSeconds;

  // ── Quote text ──────────────────────────────────────────
  const quoteText = normalizeQuote(config.quotePlain);

  const quoteWords = quoteText.split(" ").map((word, i, arr) =>
    i < arr.length - 1 ? word + " " : word,
  );

  const numWords = quoteWords.length;

  // ── Reading timing ─────────────────────────────────────
  const quoteTotalFrames = Math.max(
    30,
    (runtimeTotalReadingSeconds ?? 18) * config.fps -
      config.highlightStart -
      config.speakerDuration,
  );

  const wordDuration = quoteTotalFrames / Math.max(1, numWords);

  // ── Auto-scroll math ───────────────────────────────────
  const estimatedQuoteLines = Math.max(
    1,
    Math.ceil(
      quoteText.length / config.quoteCharsPerLine,
    ),
  );

  const quoteLinePx =
    config.fontSize * config.lineHeight;

  const speakerLinePx =
    config.speakerFontSize * 1.8;

  const estimatedContentHeight =
    speakerLinePx +
    config.speakerMarginBottom +
    estimatedQuoteLines * quoteLinePx;

  const viewportHeightPx =
    config.viewportLines * quoteLinePx;

  const needsScroll =
    estimatedContentHeight >
    viewportHeightPx + 5;

  const maxScrollPx = Math.max(
    0,
    estimatedContentHeight - viewportHeightPx,
  );

  // ── Font loading ───────────────────────────────────────
  const [handle] = useState(() =>
    delayRender("Loading Tajawal font"),
  );

  useEffect(() => {
    const font = new FontFace(
      "Tajawal",
      `url(${staticFile("fonts/Tajawal-Medium.ttf")})`,
    );

    font
      .load()
      .then(() => {
        document.fonts.add(font);
        continueRender(handle);
      })
      .catch((err) => {
        console.error(
          "Font load failed",
          err,
        );
        continueRender(handle);
      });
  }, [handle]);

  // ── Camera dolly ───────────────────────────────────────
  const cameraScale = interpolate(
    frame,
    [
      config.camera.startFrame,
      config.camera.endFrame,
    ],
    [1, config.camera.scale],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const cameraRotateX = interpolate(
    frame,
    [
      config.camera.startFrame,
      config.camera.endFrame,
    ],
    [0, config.camera.rotateX],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Reading progress ───────────────────────────────────
  const totalReadingFrames =
    config.speakerDuration +
    numWords * wordDuration;

  const elapsed = Math.max(
    0,
    frame - config.highlightStart,
  );

  const readingProgress =
    totalReadingFrames > 0
      ? Math.min(
          1,
          elapsed / totalReadingFrames,
        )
      : 1;

  // ── Scroll progress ────────────────────────────────────
  const scrollProgress = needsScroll
    ? Math.max(
        0,
        Math.min(
          1,
          (readingProgress -
            config.scrollStartFraction) /
            (1 -
              config.scrollStartFraction),
        ),
      )
    : 0;

  const scrollY =
    -scrollProgress * maxScrollPx;

  // ── Text content ───────────────────────────────────────
  const textContent = (
    <>
      {/* Speaker line */}
      <div
        style={{
          display: "block",
          marginBottom:
            config.speakerMarginBottom,
        }}
      >
        <span
          style={{
            fontSize:
              config.speakerFontSize,
            lineHeight: 1.8,
          }}
        >
          <SpeakerSweep
            text={config.speaker}
            delay={config.highlightStart}
            duration={
              config.speakerDuration
            }
            highlightRgb={
              config.colors.highlightRgb
            }
            textColor={config.colors.text}
          />
        </span>
      </div>

      {/* Quote */}
      <p
        style={{
          display: "block",
          margin: 0,
          textAlign: "justify",
          textAlignLast: "right",
          wordSpacing: "0.02em",
        }}
      >
        {quoteWords.map((word, i) => (
          <WordSweep
            key={i}
            text={word}
            delay={
              config.highlightStart +
              config.speakerDuration +
              i * wordDuration
            }
            duration={wordDuration}
            highlightRgb={
              config.colors.highlightRgb
            }
            textColor={config.colors.text}
          />
        ))}
      </p>
    </>
  );

  // ── Render ──────────────────────────────────────────────
  return (
    <AbsoluteFill
      style={{
        backgroundColor:
          config.colors.background,
        overflow: "hidden",
        perspective: 1800,
        perspectiveOrigin:
          "center center",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `scale(${cameraScale}) rotateX(${cameraRotateX}deg)`,
          transformOrigin:
            "center center",
          transformStyle: "preserve-3d",
        }}
      >
        <Img
          src={staticFile(
            config.colors.backgroundImg,
          )}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />

        <AbsoluteFill
          style={{
            direction: "rtl",
            fontFamily:
              "'Tajawal', 'Noto Naskh Arabic', 'Amiri', serif",
            color: config.colors.text,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          {/* Top decorative label */}
          <div
            style={{
              fontSize: 26,
              color: config.colors.accent,
              letterSpacing: 8,
              marginBottom:
                config.topDecorMarginBottom,
              opacity: 0.85,
            }}
          >
            {config.topLabel}
          </div>

          {/* Text block */}
          <div
            style={{
              width: config.textBlockWidth,
              fontSize: config.fontSize,
              lineHeight: config.lineHeight,
              textAlign: "justify",
              textAlignLast: "right",
              wordSpacing: "0.02em",

              ...(needsScroll
                ? {
                    height:
                      viewportHeightPx,
                    overflow: "hidden",
                    position: "relative",
                  }
                : {}),
            }}
          >
            <div
              style={
                needsScroll
                  ? {
                      transform: `translateY(${scrollY}px)`,
                      willChange:
                        "transform",
                    }
                  : undefined
              }
            >
              {textContent}
            </div>
          </div>

          {/* Footer */}
          <div
            style={{
              marginTop:
                config.footerMarginTop,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            <div
              style={{
                position: "relative",
                width: 520,
                height: 1,
                background: `linear-gradient(
                  to right,
                  transparent 0%,
                  ${config.colors.dim} 25%,
                  ${config.colors.dim} 75%,
                  transparent 100%
                )`,
                marginBottom: 24,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: -5,
                  left: "50%",
                  transform:
                    "translateX(-50%) rotate(45deg)",
                  width: 10,
                  height: 10,
                  backgroundColor:
                    config.colors.text,
                }}
              />
            </div>

            <div
              style={{
                fontSize: 28,
                color: config.colors.text,
                opacity: 0.9,
                letterSpacing: 1,
              }}
            >
              {config.source}
            </div>
          </div>
        </AbsoluteFill>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Registry exports
// =============================================================================

export const quoteDefaults = CONFIG;
export const Quote = MyAnimation;

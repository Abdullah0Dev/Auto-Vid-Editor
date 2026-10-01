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
  // ── Content ─────────────────────────────────────────────
  topLabel: "حَـدِيـث",

  isnad:
    "عَنْ أَبِي هُرَيْرَةَ رَضِيَ اللَّهُ عَنْهُ، أَنَّ رَسُولَ اللَّهِ ﷺ قَالَ:",

  matnPlain: `مَنْ نَفَّسَ عَنْ مُؤْمِنٍ كُرْبَةً مِنْ كُرَبِ الدُّنْيَا، نَفَّسَ اللَّهُ عَنْهُ كُرْبَةً مِنْ كُرَبِ يَوْمِ الْقِيَامَةِ، وَمَنْ يَسَّرَ عَلَى مُعْسِرٍ، يَسَّرَ اللَّهُ عَلَيْهِ فِي الدُّنْيَا وَالآخِرَةِ`,

  source: "رَوَاهُ مُسْلِمٌ",

  wrapInGuillemets: true,

  // ── Timing ──────────────────────────────────────────────
  fps: 30,
  totalReadingSeconds: 15 as number | null,
  highlightStart: 70,
  isnadDuration: 60,

  // ── Camera ──────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 55,
    scale: 1.13,
    rotateX: 15,
  },

  // ── Layout ──────────────────────────────────────────────
  fontSize: 46,
  isnadFontSize: 36,
  lineHeight: 2.2,
  textBlockWidth: "70%",
  topDecorMarginBottom: 50,
  isnadMarginBottom: 40,
  footerMarginTop: 70,
  viewportLines: 6,
  charsPerLineEstimate: 48,
  scrollStartFraction: 0.25,

  // ── Colors ──────────────────────────────────────────────
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

type CameraConfig = typeof CONFIG.camera;
type ColorsConfig = typeof CONFIG.colors;

export type HadithProps = Partial<
  Omit<typeof CONFIG, "camera" | "colors">
> & {
  durationInFrames?: number;

  camera?: Partial<CameraConfig>;
  colors?: Partial<ColorsConfig>;
};

// =============================================================================
// Default export used by the registry
// =============================================================================

export const hadithDefaults = CONFIG;

// =============================================================================
// Sweep
// =============================================================================

const Sweep = ({
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

export const Hadith: React.FC<HadithProps> = (
  incoming,
) => {
  const frame = useCurrentFrame();

  // ── Merge defaults + runtime props ──────────────────────
  const config = {
    ...CONFIG,
    ...(incoming ?? {}),

    camera: {
      ...CONFIG.camera,
      ...(incoming?.camera ?? {}),
    },

    colors: {
      ...CONFIG.colors,
      ...(incoming?.colors ?? {}),
    },
  };

  // ── Runtime duration ───────────────────────────────────
  // If Python sends durationInFrames but doesn't provide
  // totalReadingSeconds, use the actual render duration.
  const runtimeTotalReadingSeconds =
    incoming?.totalReadingSeconds != null
      ? incoming.totalReadingSeconds
      : typeof incoming?.durationInFrames ===
            "number" &&
          incoming.durationInFrames > 0
        ? incoming.durationInFrames /
          config.fps
        : config.totalReadingSeconds;

  // ── Matn text ───────────────────────────────────────────
  const matnText = config.wrapInGuillemets
    ? `«${config.matnPlain
        .trim()
        .replace(/^«\s*|\s*»$/g, "")
        .trim()}»`
    : config.matnPlain.trim();

  // ── Word splitting ─────────────────────────────────────
  const matnWords = matnText
    .split(" ")
    .map((word, i, arr) =>
      i < arr.length - 1
        ? word + " "
        : word,
    );

  const numWords = Math.max(
    1,
    matnWords.length,
  );

  // ── Reading timing ─────────────────────────────────────
  const matnTotalFrames = Math.max(
    30,
    (runtimeTotalReadingSeconds ?? 15) *
      config.fps -
      config.highlightStart -
      config.isnadDuration,
  );

  const wordDuration =
    matnTotalFrames / numWords;

  // ── Auto-scroll math ───────────────────────────────────
  const estimatedMatnLines = Math.max(
    1,
    Math.ceil(
      matnText.length /
        config.charsPerLineEstimate,
    ),
  );

  const matnLinePx =
    config.fontSize *
    config.lineHeight;

  const isnadLinePx =
    config.isnadFontSize * 1.8;

  const estimatedContentHeight =
    isnadLinePx +
    config.isnadMarginBottom +
    estimatedMatnLines *
      matnLinePx;

  const viewportHeightPx =
    config.viewportLines *
    matnLinePx;

  const needsScroll =
    estimatedContentHeight >
    viewportHeightPx + 5;

  const maxScrollPx = Math.max(
    0,
    estimatedContentHeight -
      viewportHeightPx,
  );

  // ── Font loading ───────────────────────────────────────
  const [handle] = useState(() =>
    delayRender(
      "Loading Tajawal font",
    ),
  );

  useEffect(() => {
    const font = new FontFace(
      "Tajawal",
      `url(${staticFile(
        "fonts/Tajawal-Medium.ttf",
      )})`,
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

  // ── Camera ─────────────────────────────────────────────
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

  const cameraRotateX =
    interpolate(
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

  // ── Scroll ─────────────────────────────────────────────
  const totalReadingFrames =
    config.isnadDuration +
    numWords * wordDuration;

  const elapsed = Math.max(
    0,
    frame - config.highlightStart,
  );

  const readingProgress =
    totalReadingFrames > 0
      ? Math.min(
          1,
          elapsed /
            totalReadingFrames,
        )
      : 1;

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
      {/* Isnad */}
      <div
        style={{
          display: "block",
          marginBottom:
            config.isnadMarginBottom,
        }}
      >
        <span
          style={{
            fontSize:
              config.isnadFontSize,
            lineHeight: 1.8,
          }}
        >
          <Sweep
            text={config.isnad}
            delay={config.highlightStart}
            duration={
              config.isnadDuration
            }
            highlightRgb={
              config.colors.highlightRgb
            }
            textColor={
              config.colors.text
            }
          />
        </span>
      </div>

      {/* Matn */}
      <p
        style={{
          display: "block",
          margin: 0,
          textAlign: "justify",
          textAlignLast: "right",
          wordSpacing: "0.02em",
        }}
      >
        {matnWords.map(
          (word, i) => (
            <Sweep
              key={i}
              text={word}
              delay={
                config.highlightStart +
                config.isnadDuration +
                i * wordDuration
              }
              duration={wordDuration}
              highlightRgb={
                config.colors
                  .highlightRgb
              }
              textColor={
                config.colors.text
              }
            />
          ),
        )}
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
          transformStyle:
            "preserve-3d",
        }}
      >
        {/* Background */}
        <Img
          src={staticFile(
            config.colors
              .backgroundImg,
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
            color:
              config.colors.text,
            display: "flex",
            flexDirection:
              "column",
            justifyContent:
              "center",
            alignItems: "center",
          }}
        >
          {/* Top label */}
          <div
            style={{
              fontSize: 26,
              color:
                config.colors.accent,
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
              width:
                config.textBlockWidth,
              fontSize:
                config.fontSize,
              lineHeight:
                config.lineHeight,
              textAlign: "justify",
              textAlignLast: "right",
              wordSpacing: "0.02em",

              ...(needsScroll
                ? {
                    height:
                      viewportHeightPx,
                    overflow: "hidden",
                    position:
                      "relative",
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
              flexDirection:
                "column",
              alignItems:
                "center",
            }}
          >
            <div
              style={{
                position:
                  "relative",
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
                  position:
                    "absolute",
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
                color:
                  config.colors.text,
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

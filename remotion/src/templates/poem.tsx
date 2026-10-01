import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { useEffect, useState } from "react";
import {
  continueRender,
  delayRender,
} from "remotion";

// =============================================================================
// ⚙️ CONFIG — default values
// =============================================================================
const CONFIG = {
  // ── Content ────────────────────────────────────────────
  poemLines: [
    {
      text1: "وَاحَرَّ قَلْبَاهُ مِمَّنْ قَلْبُهُ شَبِمُ",
      text2: "وَمَنْ بِجِسْمِي وَحَالِي عِنْدَهُ سَقَمُ",
    },
    {
      text1: "مَالِي أُكَـتِّـمُ حُبًّا قَدْ بَرَى جَسَدِي",
      text2: "وَتَدَّعِي حُبَّ سَيْفِ الدَّوْلَةِ الأُمَمُ",
    },
    {
      text1: "إِنْ كَانَ يَجْمَعُنَا حُبٌّ لِغُرَّتِهِ",
      text2: "فَلَيْتَ أَنَّا بِقَدْرِ الْحُبِّ نَقْتَسِمُ",
    },
    {
      text1: "قَدْ زُرْتُهُ وَسُيُوفُ الْهِنْدِ مُغْمَدَةٌ",
      text2: "وَقَدْ نَظَرْتُ إِلَيْهِ وَالسُّيُوفُ دَمُ",
    },
    {
      text1: "فَكَانَ أَحْسَنَ خَلْقِ اللَّهِ كُلِّهِمُ",
      text2: "وَكَانَ أَحْسَنَ مَا فِي الأَحْسَنِ الشِّيَمُ",
    },
    {
      text1: "فَوْتُ الْعَدُوِّ الَّذِي يَمَّمْتُهُ ظَفَرٌ",
      text2: "فِي طَيِّهِ أَسَفٌ فِي طَيِّهِ نِعَمُ",
    },
  ] as { text1: string; text2: string }[],

  footerLabel:
    "المتنبي - في مدح سيف الدولة",

  // ── Timing ─────────────────────────────────────────────
  fps: 30,
  totalReadingSeconds:
    180 as number | null,

  highlightStart: 70,
  highlightGap: 10,
  defaultHighlightDuration: 126.819,

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 55,
    scale: 1.13,
    rotateX: 15,
  },

  // ── Layout ─────────────────────────────────────────────
  fontSize: 54,
  lineHeight: 1.75,
  lineGap: 32,
  contentPadding: 120,
  hemistichWidth: 720,
  visibleRows: 5,
  scrollAnchorRow: 2,

  // ── Colors ─────────────────────────────────────────────
  colors: {
    text: "rgba(217, 196, 122, 0.75)",
    textReading: "rgba(217, 196, 122, 0.75)",
    accent: "#b8935a",
    dim: "#8a6f3c",
    highlight: "rgba(217, 170, 60, 0.55)",
    background: "#0a2e1c",
    backgroundImg:
      "poem-bg.jpeg",
  },
};

// =============================================================================
// Public props
// =============================================================================

type PoemLine =
  (typeof CONFIG.poemLines)[number];

type CameraConfig = typeof CONFIG.camera;
type ColorsConfig = typeof CONFIG.colors;

export type poemProps = Partial<
  Omit<
    typeof CONFIG,
    "poemLines" | "camera" | "colors"
  >
> & {
  durationInFrames?: number;

  poemLines?: PoemLine[];
  camera?: Partial<CameraConfig>;
  colors?: Partial<ColorsConfig>;
};

// =============================================================================
// Hemistich
// =============================================================================

const Hemistich = ({
  text,
  delay,
  duration,
  hemistichWidth,
  textColor,
  textReadingColor,
  highlight,
}: {
  text: string;
  delay: number;
  duration: number;
  hemistichWidth: number;
  textColor: string;
  textReadingColor: string;
  highlight: string;
}) => {
  const frame = useCurrentFrame();

  const sweep = interpolate(
    frame - delay,
    [0, duration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const isReading = frame >= delay;

  return (
    <span
      style={{
        position: "relative",
        width: hemistichWidth,
        display: "inline-block",
        textAlign: "justify",
        textAlignLast: "justify",
        whiteSpace: "nowrap",
        color: isReading
          ? textReadingColor
          : textColor,
      }}
    >
      <span
        style={{
          position: "absolute",
          top: -6,
          bottom: -6,
          right: -10,
          left: -10,
          backgroundColor: highlight,
          transform: `scaleX(${sweep})`,
          transformOrigin: "right",
          borderRadius: 4,
          zIndex: 0,
        }}
      />

      <span
        style={{
          position: "relative",
          zIndex: 1,
        }}
      >
        {text}
      </span>
    </span>
  );
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<
  poemProps
> = (props) => {
  const frame = useCurrentFrame();
  const videoConfig = useVideoConfig();

  // ── Merge defaults + runtime props ──────────────────────
  const config = {
    ...CONFIG,
    ...props,

    poemLines: props.poemLines ?? CONFIG.poemLines,

    camera: {
      ...CONFIG.camera,
      ...(props.camera ?? {}),
    },

    colors: {
      ...CONFIG.colors,
      ...(props.colors ?? {}),
    },

    // Prefer the actual Remotion composition FPS.
    fps:
      videoConfig.fps ||
      CONFIG.fps,
  };

  // ── Timing ─────────────────────────────────────────────
  const numHemistichs =
    config.poemLines.length * 2;

  const highlightDuration =
    config.totalReadingSeconds !==
        null &&
      config.totalReadingSeconds >
        0
      ? Math.max(
          10,
          (
            config.totalReadingSeconds *
              config.fps -
            config.highlightStart -
            (numHemistichs - 1) *
              config.highlightGap
          ) /
            Math.max(
              1,
              numHemistichs,
            ),
        )
      : config.defaultHighlightDuration;

  const perHemistich =
    highlightDuration +
    config.highlightGap;

  const perLine =
    perHemistich * 2;

  const rowHeight =
    config.fontSize *
      config.lineHeight +
    config.lineGap;

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
  const totalRows =
    config.poemLines.length;

  const isLongPoem =
    totalRows >
    config.visibleRows;

  const readingPos = Math.max(
    0,
    (
      frame -
      config.highlightStart
    ) /
      perLine,
  );

  const maxRowOffset = Math.max(
    0,
    totalRows -
      config.visibleRows,
  );

  let rowOffset =
    readingPos -
    config.scrollAnchorRow;

  rowOffset = Math.max(
    0,
    Math.min(
      rowOffset,
      maxRowOffset,
    ),
  );

  const scrollY =
    -rowOffset * rowHeight;

  // ── Poem rows ──────────────────────────────────────────
  const poemRows =
    config.poemLines.map(
      (line, index) => {
        const lineDelay =
          config.highlightStart +
          index * perLine;

        return (
          <div
            key={index}
            style={{
              display: "flex",
              flexDirection:
                "row",
              alignItems:
                "center",
              justifyContent:
                "center",
              gap: 44,
              fontSize:
                config.fontSize,
              lineHeight:
                config.lineHeight,
              marginBottom:
                index ===
                config.poemLines
                  .length -
                  1
                  ? 0
                  : config.lineGap,
            }}
          >
            <Hemistich
              text={line.text1}
              delay={lineDelay}
              duration={
                highlightDuration
              }
              hemistichWidth={
                config.hemistichWidth
              }
              textColor={
                config.colors.text
              }
              textReadingColor={
                config.colors
                  .textReading
              }
              highlight={
                config.colors
                  .highlight
              }
            />

            <span
              style={{
                color:
                  config.colors
                    .accent,
                fontSize:
                  config.fontSize *
                  0.55,
                opacity: 0.85,
              }}
            >
              ✽
            </span>

            <Hemistich
              text={line.text2}
              delay={
                lineDelay +
                perHemistich
              }
              duration={
                highlightDuration
              }
              hemistichWidth={
                config.hemistichWidth
              }
              textColor={
                config.colors.text
              }
              textReadingColor={
                config.colors
                  .textReading
              }
              highlight={
                config.colors
                  .highlight
              }
            />
          </div>
        );
      },
    );

  return (
    <AbsoluteFill
      style={{
        backgroundColor:
          config.colors
            .background,
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
              "'Tajawal', 'Noto Naskh Arabic', serif",
            color:
              config.colors.text,
            display: "flex",
            flexDirection:
              "column",
            justifyContent:
              "center",
            alignItems:
              "center",
            padding: `0 ${config.contentPadding}px`,
          }}
        >
          {/* Poem */}
          {isLongPoem ? (
            <div
              style={{
                height:
                  config.visibleRows *
                  rowHeight,
                width: "100%",
                overflow:
                  "hidden",
                position:
                  "relative",
              }}
            >
              <div
                style={{
                  transform: `translateY(${scrollY}px)`,
                  willChange:
                    "transform",
                }}
              >
                {poemRows}
              </div>
            </div>
          ) : (
            poemRows
          )}

          {/* Footer */}
          <div
            style={{
              marginTop: 90,
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
                marginBottom: 26,
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
                    config.colors
                      .text,
                }}
              />
            </div>

            <div
              style={{
                fontSize: 28,
                color:
                  config.colors
                    .text,
                opacity: 0.85,
                letterSpacing: 1,
              }}
            >
              {
                config.footerLabel
              }
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

export const poemDefaults =
  CONFIG;

export const Poem =
  MyAnimation;
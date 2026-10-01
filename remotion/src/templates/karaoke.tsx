import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

// =============================================================================
// 🎨 PALETTE
// =============================================================================
const PALETTE = {
  emerald: "#0B3D2E",
  navy: "#0F1B2D",
  gold: "#C9A227",
  parchment: "#F2E8D5",
  leather: "#5A3E2B",
  burgundy: "#7A1F2B",
  stone: "#3F4A4A",
  ivory: "#FAF7F0",
  copper: "#B87333",
};

// =============================================================================
// 🎭 THEMES
// =============================================================================

interface KaraokeTheme {
  background: string;
  future: string;
  active: string;
  activeAccent: string;
  past: string;
  captionBg: string;
  captionBorder: string;
}

const THEMES: Record<string, KaraokeTheme> = {
  parchment: {
    background: PALETTE.emerald,
    future: "rgba(242, 232, 213, 0.38)",
    active: "#FAF7F0",
    activeAccent: PALETTE.gold,
    past: "rgba(242, 232, 213, 0.72)",
    captionBg: "rgba(11, 61, 46, 0.82)",
    captionBorder: "rgba(201, 162, 39, 0.45)",
  },

  crimson: {
    background: PALETTE.navy,
    future: "rgba(242, 232, 213, 0.35)",
    active: "#FAF7F0",
    activeAccent: PALETTE.burgundy,
    past: "rgba(242, 232, 213, 0.68)",
    captionBg: "rgba(15, 27, 45, 0.85)",
    captionBorder: "rgba(122, 31, 43, 0.55)",
  },

  andalusian: {
    background: PALETTE.leather,
    future: "rgba(242, 232, 213, 0.4)",
    active: "#FAF7F0",
    activeAccent: PALETTE.copper,
    past: "rgba(242, 232, 213, 0.7)",
    captionBg: "rgba(90, 62, 43, 0.85)",
    captionBorder: "rgba(184, 115, 51, 0.55)",
  },

  night: {
    background: PALETTE.navy,
    future: "rgba(250, 247, 240, 0.35)",
    active: "#FAF7F0",
    activeAccent: PALETTE.gold,
    past: "rgba(250, 247, 240, 0.72)",
    captionBg: "rgba(15, 27, 45, 0.9)",
    captionBorder: "rgba(201, 162, 39, 0.5)",
  },
};

// =============================================================================
// ⚙️ CONFIG — default values
// =============================================================================

const CONFIG = {
  // ── Background ─────────────────────────────────────────
  background: "poem-bg.jpeg" as string | null,

  // ── Theme ──────────────────────────────────────────────
  theme: "parchment" as keyof typeof THEMES,

  // ── Animation style ────────────────────────────────────
  style: "pop" as
    | "underline"
    | "rise"
    | "pop"
    | "blurFocus"
    | "dualTone"
    | "wave",

  // ── Content ────────────────────────────────────────────
  text:
    "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ",

  // ── Timing ─────────────────────────────────────────────
  timing: "auto" as "auto" | "manual",
  readingSeconds: 6,
  manualTimestamps: [
    0,
    0.5,
    0.9,
    1.3,
    1.7,
    2.1,
    2.6,
    3.1,
  ] as number[],
  activeDurationSeconds: 0.4,

  // ── Reveal ─────────────────────────────────────────────
  revealStart: 20,
  containerEnter: 40,

  // ── Layout ────────────────────────────────────────────
  bottomPercent: 12,
  fontSize: 52,

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 60,
    scale: 1.14,
    rotateX: 10,
  },

  // ── Header ─────────────────────────────────────────────
  header:
    "سُورَةُ البَقَرَة — الآيَة ٢٥٥" as string | null,

  // ── FPS ────────────────────────────────────────────────
  fps: 30,
};

// =============================================================================
// Public props
// =============================================================================

type CameraConfig = typeof CONFIG.camera;

export type karaokeProps = Partial<
  Omit<typeof CONFIG, "camera">
> & {
  durationInFrames?: number;
  camera?: Partial<CameraConfig>;
};

// =============================================================================
// Timing helper
// =============================================================================

const toWords = (text: string): string[] =>
  text.trim().split(/\s+/);

const computeWordTimings = (
  wordCount: number,
  config: typeof CONFIG,
): {
  startFrames: number[];
  endFrames: number[];
} => {
  const startFrames: number[] = [];
  const endFrames: number[] = [];

  if (wordCount <= 0) {
    return {
      startFrames,
      endFrames,
    };
  }

  if (config.timing === "manual") {
    for (let i = 0; i < wordCount; i++) {
      const tSec =
        config.manualTimestamps[i] ??
        i * 0.5;

      const startFrame =
        config.revealStart +
        Math.round(
          tSec * config.fps,
        );

      const endFrame =
        startFrame +
        Math.round(
          config.activeDurationSeconds *
            config.fps,
        );

      startFrames.push(startFrame);
      endFrames.push(endFrame);
    }
  } else {
    const totalFrames = Math.round(
      config.readingSeconds *
        config.fps,
    );

    const wordDurFrames =
      totalFrames / wordCount;

    const activeDurFrames =
      Math.round(
        config.activeDurationSeconds *
          config.fps,
      );

    for (
      let i = 0;
      i < wordCount;
      i++
    ) {
      const startFrame =
        config.revealStart +
        Math.round(
          i * wordDurFrames,
        );

      const activeLen = Math.min(
        Math.round(wordDurFrames),
        activeDurFrames,
      );

      const endFrame =
        startFrame + activeLen;

      startFrames.push(startFrame);
      endFrames.push(endFrame);
    }
  }

  return {
    startFrames,
    endFrames,
  };
};

// =============================================================================
// Word state resolution
// =============================================================================

interface WordState {
  isFuture: boolean;
  isActive: boolean;
  isPast: boolean;
  activeProgress: number;
  pastProgress: number;
}

const useWordState = (
  startFrame: number,
  endFrame: number,
): WordState => {
  const frame = useCurrentFrame();

  const isFuture =
    frame < startFrame;

  const isActive =
    frame >= startFrame &&
    frame < endFrame;

  const isPast =
    frame >= endFrame;

  const activeProgress =
    interpolate(
      frame,
      [startFrame, startFrame + 6],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  const pastProgress =
    interpolate(
      frame,
      [endFrame, endFrame + 10],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  return {
    isFuture,
    isActive,
    isPast,
    activeProgress,
    pastProgress,
  };
};

// =============================================================================
// STYLE 1 — Underline
// =============================================================================

const UnderlineWord = ({
  text,
  startFrame,
  endFrame,
  theme,
}: {
  text: string;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
}) => {
  const {
    isFuture,
    isActive,
    isPast,
    activeProgress,
  } =
    useWordState(
      startFrame,
      endFrame,
    );

  const color = isFuture
    ? theme.future
    : isActive
      ? theme.active
      : theme.past;

  const lineWidth = isPast
    ? 100
    : isActive
      ? activeProgress * 100
      : 0;

  const lineOpacity = isFuture
    ? 0
    : isActive
      ? activeProgress
      : 0.7;

  const pulse = isActive
    ? 1 +
      0.04 *
        Math.sin(
          activeProgress *
            Math.PI,
        )
    : 1;

  return (
    <span
      style={{
        position: "relative",
        display: "inline-block",
        color,
        padding: "0.05em 0.15em",
        margin: "0 0.08em",
        transform: `translateY(${
          isActive
            ? -2 * activeProgress
            : 0
        }px) scale(${pulse})`,
        textShadow: isActive
          ? `0 0 8px ${theme.activeAccent}88`
          : "0 2px 4px rgba(0,0,0,0.5)",
        transition: "none",
      }}
    >
      {text}

      <span
        style={{
          position: "absolute",
          bottom: -2,
          right: 0,
          height: 2.5,
          width: `${lineWidth}%`,
          backgroundColor:
            theme.activeAccent,
          opacity: lineOpacity,
          borderRadius: 2,
          boxShadow: isActive
            ? `0 0 8px ${theme.activeAccent}`
            : "none",
        }}
      />
    </span>
  );
};

// =============================================================================
// STYLE 2 — Rise
// =============================================================================

const RiseWord = ({
  text,
  startFrame,
  endFrame,
  theme,
}: {
  text: string;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
}) => {
  const {
    isFuture,
    isActive,
    isPast,
    activeProgress,
  } =
    useWordState(
      startFrame,
      endFrame,
    );

  const y = isFuture
    ? 20
    : isActive
      ? 20 *
        (1 -
          activeProgress)
      : 0;

  const opacity = isFuture
    ? 0
    : isActive
      ? activeProgress
      : 1;

  const color = isActive
    ? theme.active
    : isPast
      ? theme.past
      : theme.future;

  return (
    <span
      style={{
        display: "inline-block",
        opacity,
        transform: `translateY(${y}px)`,
        color,
        padding: "0.05em 0.15em",
        margin: "0 0.08em",
        textShadow: isActive
          ? `0 0 12px ${theme.activeAccent}99, 0 2px 6px rgba(0,0,0,0.5)`
          : "0 2px 4px rgba(0,0,0,0.5)",
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// STYLE 3 — Pop
// =============================================================================

const PopWord = ({
  text,
  startFrame,
  endFrame,
  theme,
  fps,
}: {
  text: string;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
  fps: number;
}) => {
  const frame = useCurrentFrame();

  const {
    isFuture,
    isPast,
  } =
    useWordState(
      startFrame,
      endFrame,
    );

  const pop = spring({
    frame: frame - startFrame,
    fps,
    config: {
      damping: 8,
      stiffness: 180,
      mass: 0.6,
    },
  });

  const scale = isFuture
    ? 0.75
    : isPast
      ? 1
      : 0.75 +
        0.25 * pop +
        0.15 *
          pop *
          (1 - pop);

  const color = isFuture
    ? theme.future
    : isPast
      ? theme.past
      : theme.active;

  return (
    <span
      style={{
        display: "inline-block",
        transform: `scale(${scale})`,
        transformOrigin:
          "center center",
        color,
        padding: "0.05em 0.15em",
        margin: "0 0.08em",
        textShadow:
          !isFuture && !isPast
            ? `0 0 16px ${theme.activeAccent}, 0 2px 6px rgba(0,0,0,0.5)`
            : "0 2px 4px rgba(0,0,0,0.5)",
        fontWeight: 700,
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// STYLE 4 — Blur Focus
// =============================================================================

const BlurFocusWord = ({
  text,
  startFrame,
  endFrame,
  theme,
}: {
  text: string;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
}) => {
  const {
    isFuture,
    isActive,
    activeProgress,
    pastProgress,
  } =
    useWordState(
      startFrame,
      endFrame,
    );

  const blur = isFuture
    ? 4
    : isActive
      ? 4 *
        (1 -
          activeProgress)
      : 1.2 *
        pastProgress;

  const opacity = isFuture
    ? 0.5
    : isActive
      ? 0.5 +
        0.5 *
          activeProgress
      : 0.85 -
        0.15 *
          pastProgress;

  const color = isActive
    ? theme.active
    : theme.future;

  return (
    <span
      style={{
        display: "inline-block",
        color,
        opacity,
        filter: `blur(${blur}px)`,
        padding: "0.05em 0.15em",
        margin: "0 0.08em",
        textShadow: isActive
          ? `0 0 10px ${theme.activeAccent}88`
          : "0 2px 4px rgba(0,0,0,0.4)",
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// STYLE 5 — Dual Tone
// =============================================================================

const DualToneWord = ({
  text,
  startFrame,
  endFrame,
  theme,
}: {
  text: string;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
}) => {
  const {
    isFuture,
    isActive,
    activeProgress,
    pastProgress,
  } =
    useWordState(
      startFrame,
      endFrame,
    );

  const bgScale = isFuture
    ? 0
    : isActive
      ? activeProgress
      : 1 -
        pastProgress *
          0.85;

  const color = isFuture
    ? theme.future
    : isActive
      ? theme.background
      : theme.past;

  return (
    <span
      style={{
        position: "relative",
        display: "inline-block",
        padding: "0.12em 0.28em",
        margin: "0 0.06em",
        color,
        zIndex: 1,
        textShadow: isActive
          ? "none"
          : "0 2px 4px rgba(0,0,0,0.5)",
        fontWeight: 600,
        transition: "none",
      }}
    >
      <span
        style={{
          position: "absolute",
          inset: 0,
          backgroundColor:
            theme.activeAccent,
          borderRadius: 8,
          transform: `scale(${bgScale})`,
          transformOrigin:
            "center center",
          zIndex: -1,
          boxShadow: isActive
            ? `0 4px 20px ${theme.activeAccent}88`
            : "none",
        }}
      />

      {text}
    </span>
  );
};

// =============================================================================
// STYLE 6 — Wave
// =============================================================================

const WaveWord = ({
  text,
  startFrame,
  endFrame,
  theme,
  index,
}: {
  text: string;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
  index: number;
}) => {
  const frame = useCurrentFrame();

  const {
    isFuture,
    isActive,
    isPast,
  } =
    useWordState(
      startFrame,
      endFrame,
    );

  const waveAmplitude =
    isActive ? 8 : 2.5;

  const waveY =
    Math.sin(
      (frame -
        startFrame) *
        0.18 +
        index * 0.6,
    ) *
    waveAmplitude;

  const color = isFuture
    ? theme.future
    : isActive
      ? theme.active
      : theme.past;

  const opacity = isFuture
    ? 0.55
    : isActive
      ? 1
      : 0.9;

  return (
    <span
      style={{
        display: "inline-block",
        transform: `translateY(${waveY}px)`,
        color,
        opacity,
        padding: "0.05em 0.15em",
        margin: "0 0.08em",
        textShadow: isActive
          ? `0 0 14px ${theme.activeAccent}cc, 0 2px 6px rgba(0,0,0,0.5)`
          : "0 2px 4px rgba(0,0,0,0.5)",
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// Dispatch
// =============================================================================

const KaraokeWord = ({
  text,
  index,
  startFrame,
  endFrame,
  theme,
  style,
  fps,
}: {
  text: string;
  index: number;
  startFrame: number;
  endFrame: number;
  theme: KaraokeTheme;
  style: typeof CONFIG.style;
  fps: number;
}) => {
  switch (style) {
    case "underline":
      return (
        <UnderlineWord
          text={text}
          startFrame={startFrame}
          endFrame={endFrame}
          theme={theme}
        />
      );

    case "rise":
      return (
        <RiseWord
          text={text}
          startFrame={startFrame}
          endFrame={endFrame}
          theme={theme}
        />
      );

    case "pop":
      return (
        <PopWord
          text={text}
          startFrame={startFrame}
          endFrame={endFrame}
          theme={theme}
          fps={fps}
        />
      );

    case "blurFocus":
      return (
        <BlurFocusWord
          text={text}
          startFrame={startFrame}
          endFrame={endFrame}
          theme={theme}
        />
      );

    case "dualTone":
      return (
        <DualToneWord
          text={text}
          startFrame={startFrame}
          endFrame={endFrame}
          theme={theme}
        />
      );

    case "wave":
      return (
        <WaveWord
          text={text}
          index={index}
          startFrame={startFrame}
          endFrame={endFrame}
          theme={theme}
        />
      );

    default:
      return null;
  }
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<
  karaokeProps
> = (props) => {
  const frame = useCurrentFrame();
  const videoConfig = useVideoConfig();

  // ── Merge defaults + runtime props ──────────────────────
  const config = {
    ...CONFIG,
    ...props,

    camera: {
      ...CONFIG.camera,
      ...(props.camera ?? {}),
    },

    // Keep the composition's actual Remotion FPS
    // when possible, while retaining CONFIG as the default.
    fps: videoConfig.fps || CONFIG.fps,
  };

  // ── Theme ───────────────────────────────────────────────
  const theme =
    THEMES[config.theme] ??
    THEMES.parchment;

  // ── Words ───────────────────────────────────────────────
  const words = toWords(config.text);

  // ── Word timings ────────────────────────────────────────
  const { startFrames, endFrames } =
    computeWordTimings(
      words.length,
      config,
    );

  // ── Camera dolly ───────────────────────────────────────
  const cameraScale =
    interpolate(
      frame,
      [
        config.camera.startFrame,
        config.camera.endFrame,
      ],
      [1, config.camera.scale],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
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
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  // ── Caption container entry ─────────────────────────────
  const containerOpacity =
    interpolate(
      frame,
      [
        config.containerEnter - 20,
        config.containerEnter + 10,
      ],
      [0, 1],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  const containerY =
    interpolate(
      frame,
      [
        config.containerEnter - 20,
        config.containerEnter + 10,
      ],
      [24, 0],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  // ── Header reveal ───────────────────────────────────────
  const headerOpacity =
    interpolate(
      frame,
      [20, 50],
      [0, 1],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  return (
    <AbsoluteFill
      style={{
        backgroundColor:
          theme.background,
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
        {config.background && (
          <>
            <Img
              src={staticFile(
                config.background,
              )}
              style={{
                position:
                  "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit:
                  "cover",
              }}
            />

            <div
              style={{
                position:
                  "absolute",
                inset: 0,
                background: `linear-gradient(
                  180deg,
                  ${theme.background}CC 0%,
                  ${theme.background}99 40%,
                  ${theme.background}DD 100%
                )`,
                mixBlendMode:
                  "multiply",
              }}
            />
          </>
        )}

        {/* Vignette */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.55) 100%)",
          }}
        />

        {/* Header */}
        {config.header && (
          <div
            style={{
              position:
                "absolute",
              top: "6%",
              left: "50%",
              transform:
                "translateX(-50%)",
              opacity:
                headerOpacity,
              direction: "rtl",
              fontFamily:
                "'Tajawal', 'Noto Naskh Arabic', serif",
              fontSize: 22,
              color: PALETTE.gold,
              letterSpacing: 6,
              textShadow:
                "0 2px 10px rgba(0,0,0,0.7)",
              whiteSpace:
                "nowrap",
            }}
          >
            {config.header}
          </div>
        )}

        {/* Caption container */}
        <div
          style={{
            position:
              "absolute",
            left: "50%",
            bottom: `${config.bottomPercent}%`,
            transform: `translate(-50%, ${containerY}px)`,
            opacity:
              containerOpacity,
            width: "82%",
            maxWidth: 1500,
            display: "flex",
            justifyContent:
              "center",
          }}
        >
          <div
            style={{
              direction: "rtl",
              fontFamily:
                "'Tajawal', 'Noto Naskh Arabic', serif",
              fontSize:
                config.fontSize,
              fontWeight: 600,
              lineHeight: 1.9,
              textAlign: "center",
              padding: "26px 44px",
              backgroundColor:
                theme.captionBg,
              border: `1.5px solid ${theme.captionBorder}`,
              borderRadius: 14,
              boxShadow:
                "0 8px 32px rgba(0,0,0,0.6), inset 0 0 40px rgba(0,0,0,0.15)",
              backdropFilter:
                "blur(6px)",
              WebkitBackdropFilter:
                "blur(6px)",
              maxWidth: "100%",
              minHeight: 100,
            }}
          >
            {words.map(
              (word, i) => (
                <KaraokeWord
                  key={i}
                  text={word}
                  index={i}
                  startFrame={
                    startFrames[i]
                  }
                  endFrame={
                    endFrames[i]
                  }
                  theme={theme}
                  style={
                    config.style
                  }
                  fps={config.fps}
                />
              ),
            )}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Registry exports
// =============================================================================

export const karaokeDefaults =
  CONFIG;

export const Karaoke =
  MyAnimation;

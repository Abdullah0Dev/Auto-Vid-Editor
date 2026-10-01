import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { Audio } from "@remotion/media";
import {
  useWindowedAudioData,
  visualizeAudio,
  visualizeAudioWaveform,
  createSmoothSvgPath,
} from "@remotion/media-utils";

// =============================================================================
// ⚙️ CONFIG — default values
// =============================================================================
const CONFIG = {
  // --- Audio ---
  audioSrc: "audio/test.wav",
  background: "poem-bg.jpeg",

  // --- Visualizer mode ---
  mode: "waveform" as "spectrum" | "waveform",

  // --- Spectrum settings ---
  spectrum: {
    barCount: 128,
    mirror: true,
    barWidth: 4,
    barGap: 2,
    maxHeight: 260,
    cornerRadius: 2,
  },

  // --- Waveform settings ---
  waveform: {
    samples: 256,
    windowInSeconds: 0.5,
    amplitude: 1.2,
    strokeWidth: 3,
  },

  // --- Bass-reactive ambient glow ---
  bassGlow: {
    enabled: true,
    maxOpacity: 0.35,
    lowFreqBins: 32,
    intensityMultiplier: 3,
  },

  // --- Optional text overlays ---
  title: {
    speaker: "الإِمَامُ البُخَارِيّ",
    subtitle: "صَحِيحُ البُخَارِيّ",
  } as { speaker?: string; subtitle?: string } | null,

  // --- Camera ---
  camera: {
    startFrame: 10,
    endFrame: 70,
    scale: 1.14,
    rotateX: 10,
  },

  // --- Layout ---
  visualizerY: "58%",

  // --- Palette ---
  colors: {
    text: "rgba(240, 222, 165, 0.95)",
    accent: "#e8c874",
    dim: "#8a6f3c",
    soft: "rgba(217, 196, 122, 0.7)",
    barLow: "#f5e5a8",
    barHigh: "#b8935a",
    barGlow: "rgba(232, 200, 116, 0.55)",
    background: "#0a2e1c",
  },
};

// =============================================================================
// Public props
// =============================================================================

type SpectrumConfig = typeof CONFIG.spectrum;
type WaveformConfig = typeof CONFIG.waveform;
type BassGlowConfig = typeof CONFIG.bassGlow;
type CameraConfig = typeof CONFIG.camera;
type TitleConfig = NonNullable<typeof CONFIG.title>;
type ColorsConfig = typeof CONFIG.colors;

export type audioVisualizerProps = Partial<
  Omit<
    typeof CONFIG,
    "spectrum" | "waveform" | "bassGlow" | "title" | "camera" | "colors"
  >
> & {
  durationInFrames?: number;

  spectrum?: Partial<SpectrumConfig>;
  waveform?: Partial<WaveformConfig>;
  bassGlow?: Partial<BassGlowConfig>;
  title?: Partial<TitleConfig> | null;
  camera?: Partial<CameraConfig>;
  colors?: Partial<ColorsConfig>;
};

// =============================================================================
// Spectrum — mirrored, RTL-first bar visualizer
// =============================================================================

const SpectrumVisualizer = ({
  audioSrc,
  barCount,
  mirror,
  barWidth,
  barGap,
  maxHeight,
  cornerRadius,
  bassEnabled,
  bassBins,
  bassMultiplier,
  bassMaxOpacity,
  visualizerY,
  barLowColor,
  barHighColor,
  glowColor,
}: {
  audioSrc: string;
  barCount: number;
  mirror: boolean;
  barWidth: number;
  barGap: number;
  maxHeight: number;
  cornerRadius: number;
  bassEnabled: boolean;
  bassBins: number;
  bassMultiplier: number;
  bassMaxOpacity: number;
  visualizerY: string | number;
  barLowColor: string;
  barHighColor: string;
  glowColor: string;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const { audioData, dataOffsetInSeconds } =
    useWindowedAudioData({
      src: audioSrc,
      frame,
      fps,
      windowInSeconds: 30,
    });

  if (!audioData) return null;

  const frequencies = visualizeAudio({
    fps,
    frame,
    audioData,
    numberOfSamples: barCount,
    optimizeFor: "speed",
    dataOffsetInSeconds,
  });

  const bassEnergy = bassEnabled
    ? (() => {
        const low = frequencies.slice(0, bassBins);

        if (!low.length) return 0;

        const avg =
          low.reduce((a, b) => a + b, 0) /
          low.length;

        return Math.min(
          1,
          avg * bassMultiplier,
        );
      })()
    : 0;

  const display = mirror
    ? [
        ...frequencies.slice(1).reverse(),
        ...frequencies,
      ]
    : frequencies;

  const totalWidth =
    display.length * (barWidth + barGap) -
    barGap;

  return (
    <div
      style={{
        position: "absolute",
        top: visualizerY,
        left: "50%",
        transform: "translate(-50%, -50%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: totalWidth,
        height: maxHeight,
        gap: barGap,
      }}
    >
      {/* Bass ambient glow */}
      {bassEnabled && (
        <div
          style={{
            position: "absolute",
            inset: -120,
            background: `radial-gradient(
              ellipse at center,
              rgba(232, 200, 116, ${
                bassEnergy * bassMaxOpacity
              }) 0%,
              transparent 65%
            )`,
            filter: "blur(30px)",
            pointerEvents: "none",
          }}
        />
      )}

      {display.map((value, i) => {
        const h = Math.max(
          2,
          value * maxHeight,
        );

        const t =
          Math.abs(
            i - display.length / 2,
          ) /
          (display.length / 2);

        // Parse RGB values from configured colors when possible.
        // Fallback keeps the original gradient behavior.
        const lowRgb =
          parseRgb(barLowColor) ?? [245, 229, 168];

        const highRgb =
          parseRgb(barHighColor) ?? [184, 147, 90];

        const r = Math.round(
          lowRgb[0] +
            (highRgb[0] - lowRgb[0]) * t,
        );

        const g = Math.round(
          lowRgb[1] +
            (highRgb[1] - lowRgb[1]) * t,
        );

        const b = Math.round(
          lowRgb[2] +
            (highRgb[2] - lowRgb[2]) * t,
        );

        const color = `rgb(${r}, ${g}, ${b})`;

        return (
          <div
            key={i}
            style={{
              width: barWidth,
              height: h,
              borderRadius: cornerRadius,
              backgroundColor: color,
              boxShadow: `0 0 ${
                8 + value * 14
              }px ${withAlpha(
                glowColor,
                0.25 + value * 0.5,
              )}`,
              alignSelf: "center",
            }}
          />
        );
      })}
    </div>
  );
};

// =============================================================================
// Waveform — oscilloscope line, RTL flow
// =============================================================================

const WaveformVisualizer = ({
  audioSrc,
  samples,
  windowInSeconds,
  amplitude,
  strokeWidth,
  bassEnabled,
  visualizerY,
  barLowColor,
  barHighColor,
  softColor,
  glowColor,
}: {
  audioSrc: string;
  samples: number;
  windowInSeconds: number;
  amplitude: number;
  strokeWidth: number;
  bassEnabled: boolean;
  visualizerY: string | number;
  barLowColor: string;
  barHighColor: string;
  softColor: string;
  glowColor: string;
}) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();

  const { audioData, dataOffsetInSeconds } =
    useWindowedAudioData({
      src: audioSrc,
      frame,
      fps,
      windowInSeconds: 30,
    });

  if (!audioData) return null;

  const waveform =
    visualizeAudioWaveform({
      fps,
      frame,
      audioData,
      numberOfSamples: samples,
      windowInSeconds,
      channel: 0,
      dataOffsetInSeconds,
    });

  const HEIGHT = 400;
  const displayWidth = width * 0.78;
  const startX =
    (width - displayWidth) / 2;

  const path = createSmoothSvgPath({
    points: waveform.map((y, i) => ({
      x:
        startX +
        (i /
          Math.max(
            1,
            waveform.length - 1,
          )) *
          displayWidth,
      y:
        HEIGHT / 2 +
        ((y * HEIGHT) / 2) *
          amplitude,
    })),
  });

  return (
    <div
      style={{
        position: "absolute",
        top: visualizerY,
        left: "50%",
        transform:
          "translate(-50%, -50%)",
        width: displayWidth,
        height: HEIGHT,
      }}
    >
      {/* Bass glow */}
      {bassEnabled && (
        <div
          style={{
            position: "absolute",
            inset: -100,
            background: `radial-gradient(
              ellipse at center,
              ${withAlpha(glowColor, 0.18)} 0%,
              transparent 65%
            )`,
            filter: "blur(30px)",
            pointerEvents: "none",
          }}
        />
      )}

      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        style={{
          width: "100%",
          height: "100%",
          overflow: "visible",
        }}
      >
        <defs>
          <linearGradient
            id="waveGrad"
            x1="0"
            y1="0"
            x2="1"
            y2="0"
          >
            <stop
              offset="0%"
              stopColor={barHighColor}
            />
            <stop
              offset="50%"
              stopColor={barLowColor}
            />
            <stop
              offset="100%"
              stopColor={barHighColor}
            />
          </linearGradient>

          <filter
            id="waveGlow"
            x="-20%"
            y="-20%"
            width="140%"
            height="140%"
          >
            <feGaussianBlur
              stdDeviation="4"
              result="blur"
            />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Ghost center line */}
        <line
          x1={startX}
          y1={HEIGHT / 2}
          x2={startX + displayWidth}
          y2={HEIGHT / 2}
          stroke={withAlpha(
            glowColor,
            0.15,
          )}
          strokeWidth={1}
          strokeDasharray="4 6"
        />

        {/* Animated waveform */}
        <path
          d={path}
          fill="none"
          stroke="url(#waveGrad)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          filter="url(#waveGlow)"
        />
      </svg>
    </div>
  );
};

// =============================================================================
// Title overlay
// =============================================================================

const TitleOverlay = ({
  speaker,
  subtitle,
  textColor,
  softColor,
  glowColor,
}: {
  speaker?: string;
  subtitle?: string;
  textColor: string;
  softColor: string;
  glowColor: string;
}) => {
  const frame = useCurrentFrame();

  const speakerOpacity = interpolate(
    frame,
    [20, 55],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const subtitleOpacity = interpolate(
    frame,
    [35, 70],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return (
    <div
      style={{
        position: "absolute",
        top: "22%",
        left: "50%",
        transform: "translateX(-50%)",
        direction: "rtl",
        textAlign: "center",
        fontFamily:
          "'Tajawal', 'Noto Naskh Arabic', serif",
        pointerEvents: "none",
      }}
    >
      {speaker && (
        <div
          style={{
            fontSize: 52,
            color: textColor,
            letterSpacing: 4,
            marginBottom: 12,
            textShadow: `0 4px 18px rgba(0,0,0,0.7),
              0 0 40px ${withAlpha(
                glowColor,
                0.2,
              )}`,
            opacity: speakerOpacity,
          }}
        >
          {speaker}
        </div>
      )}

      {subtitle && (
        <div
          style={{
            fontSize: 26,
            color: softColor,
            letterSpacing: 6,
            opacity: subtitleOpacity,
            textShadow:
              "0 2px 8px rgba(0,0,0,0.6)",
          }}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
};

// =============================================================================
// Color helpers
// =============================================================================

const parseRgb = (
  value: string,
): [number, number, number] | null => {
  const rgb = value.match(
    /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i,
  );

  if (!rgb) return null;

  return [
    Number(rgb[1]),
    Number(rgb[2]),
    Number(rgb[3]),
  ];
};

const withAlpha = (
  value: string,
  alpha: number,
): string => {
  const rgb = parseRgb(value);

  if (rgb) {
    return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
  }

  return value;
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<
  audioVisualizerProps
> = (props) => {
  const frame = useCurrentFrame();

  // ── Merge defaults + runtime props ──────────────────────
  const config = useMemo(
    () => ({
      ...CONFIG,
      ...props,

      spectrum: {
        ...CONFIG.spectrum,
        ...(props.spectrum ?? {}),
      },

      waveform: {
        ...CONFIG.waveform,
        ...(props.waveform ?? {}),
      },

      bassGlow: {
        ...CONFIG.bassGlow,
        ...(props.bassGlow ?? {}),
      },

      camera: {
        ...CONFIG.camera,
        ...(props.camera ?? {}),
      },

      colors: {
        ...CONFIG.colors,
        ...(props.colors ?? {}),
      },

      // null must remain null when explicitly supplied.
      title:
        props.title === null
          ? null
          : {
              ...CONFIG.title,
              ...(props.title ?? {}),
            },
    }),
    [props],
  );

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

  const audioSrc = staticFile(
    config.audioSrc,
  );

  return (
    <AbsoluteFill
      style={{
        backgroundColor:
          config.colors.background,
        overflow: "hidden",
        perspective: 2000,
        perspectiveOrigin:
          "center center",
      }}
    >
      {/* === Audio === */}
      <Audio src={audioSrc} />

      {/* === Camera rig === */}
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
        {/* Background */}
        <Img
          src={staticFile(
            config.background,
          )}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />

        {/* Palette tint */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(180deg, rgba(10,46,28,0.6) 0%, rgba(10,46,28,0.35) 40%, rgba(10,46,28,0.7) 100%)",
            mixBlendMode: "multiply",
          }}
        />

        {/* Vignette */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.55) 100%)",
          }}
        />

        {/* Title overlay */}
        {config.title && (
          <TitleOverlay
            speaker={
              config.title.speaker
            }
            subtitle={
              config.title.subtitle
            }
            textColor={
              config.colors.text
            }
            softColor={
              config.colors.soft
            }
            glowColor={
              config.colors.barGlow
            }
          />
        )}

        {/* Visualizer */}
        {config.mode === "spectrum" ? (
          <SpectrumVisualizer
            audioSrc={audioSrc}
            barCount={
              config.spectrum.barCount
            }
            mirror={
              config.spectrum.mirror
            }
            barWidth={
              config.spectrum.barWidth
            }
            barGap={
              config.spectrum.barGap
            }
            maxHeight={
              config.spectrum.maxHeight
            }
            cornerRadius={
              config.spectrum.cornerRadius
            }
            bassEnabled={
              config.bassGlow.enabled
            }
            bassBins={
              config.bassGlow.lowFreqBins
            }
            bassMultiplier={
              config.bassGlow
                .intensityMultiplier
            }
            bassMaxOpacity={
              config.bassGlow.maxOpacity
            }
            visualizerY={
              config.visualizerY
            }
            barLowColor={
              config.colors.barLow
            }
            barHighColor={
              config.colors.barHigh
            }
            glowColor={
              config.colors.barGlow
            }
          />
        ) : (
          <WaveformVisualizer
            audioSrc={audioSrc}
            samples={
              config.waveform.samples
            }
            windowInSeconds={
              config.waveform
                .windowInSeconds
            }
            amplitude={
              config.waveform.amplitude
            }
            strokeWidth={
              config.waveform.strokeWidth
            }
            bassEnabled={
              config.bassGlow.enabled
            }
            visualizerY={
              config.visualizerY
            }
            barLowColor={
              config.colors.barLow
            }
            barHighColor={
              config.colors.barHigh
            }
            softColor={
              config.colors.soft
            }
            glowColor={
              config.colors.barGlow
            }
          />
        )}

        {/* Footer divider + attribution */}
        <div
          style={{
            position: "absolute",
            bottom: "6%",
            left: "50%",
            transform:
              "translateX(-50%)",
            direction: "rtl",
            fontFamily:
              "'Tajawal', 'Noto Naskh Arabic', serif",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              position: "relative",
              width: 420,
              height: 1,
              background: `linear-gradient(
                to right,
                transparent 0%,
                ${config.colors.dim} 25%,
                ${config.colors.dim} 75%,
                transparent 100%
              )`,
              marginBottom: 16,
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
              fontSize: 18,
              color: config.colors.soft,
              opacity: 0.85,
              letterSpacing: 3,
            }}
          >
            ▪ ▪ ▪
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Registry exports
// =============================================================================

export const audioVisualizerDefaults =
  CONFIG;

export const AudioVisualizer = MyAnimation;
import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  interpolate,
  Easing,
} from "remotion";
import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

// =============================================================================
// ⚙️ CONFIG — default values
// =============================================================================
const CONFIG = {
  // ── Background ─────────────────────────────────────────
  background: "poem-bg.jpeg",

  // ── Counter ────────────────────────────────────────────
  value: 900000,
  prefix: "",
  suffix: "+",

  // ── Labels ─────────────────────────────────────────────
  label: "حَدِيثٍ حَفِظَهَا الإِمَامُ البُخَارِيّ",
  subLabel: "صَحِيحُ البُخَارِيّ — المُسْنَدُ الصَّحِيح",

  // ── Number formatting ──────────────────────────────────
  numberFormat: "arabic" as "arabic" | "western",

  thousandsSeparator: "," as "," | "٬" | "",

  // ── Top decorative label ───────────────────────────────
  topLabel: "فِي رِحْلَةِ عُمْرِهِ" as string | null,

  // ── Counting curve ─────────────────────────────────────
  curve: "easeOut" as
    | "linear"
    | "easeOut"
    | "easeInOut",

  // ── Timing ─────────────────────────────────────────────
  fps: 30,
  revealStart: 40,
  countDuration: 90,
  labelDelay: 120,
  subLabelDelay: 150,

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 60,
    scale: 1.14,
    rotateX: 10,
  },

  // ── Colors ─────────────────────────────────────────────
  colors: {
    text: "rgba(240, 222, 165, 0.95)",
    accent: "#e8c874",
    dim: "#8a6f3c",
    soft: "rgba(217, 196, 122, 0.85)",
    bright: "#f5e5a8",
    background: "#0a2e1c",
    glow: "#e8c874",
  },
};

// =============================================================================
// Public props
// =============================================================================

type CameraConfig = typeof CONFIG.camera;
type ColorsConfig = typeof CONFIG.colors;

export type counterProps = Partial<
  Omit<typeof CONFIG, "camera" | "colors">
> & {
  durationInFrames?: number;

  camera?: Partial<CameraConfig>;
  colors?: Partial<ColorsConfig>;
};

// =============================================================================
// Number formatting helpers
// =============================================================================

const ARABIC_DIGITS = [
  "٠",
  "١",
  "٢",
  "٣",
  "٤",
  "٥",
  "٦",
  "٧",
  "٨",
  "٩",
];

const toArabicDigits = (n: number): string =>
  String(n)
    .split("")
    .map((c) => {
      const d = Number(c);
      return Number.isNaN(d)
        ? c
        : ARABIC_DIGITS[d];
    })
    .join("");

const formatNumber = (
  n: number,
  format: "arabic" | "western",
  separator: "," | "٬" | "",
): string => {
  const rounded = Math.floor(n);

  const raw = rounded.toString();

  const withSeparator = separator
    ? raw.replace(
        /\B(?=(\d{3})+(?!\d))/g,
        separator,
      )
    : raw;

  if (format === "arabic") {
    return toArabicDigits(
      Number(
        withSeparator.replace(
          /[٬,]/g,
          "",
        ),
      ),
    ).replace(
      /\B(?=(\d{3})+(?!\d))/g,
      separator,
    );
  }

  return withSeparator;
};

// =============================================================================
// Easing curves
// =============================================================================

const getEasedProgress = (
  frame: number,
  start: number,
  duration: number,
  curve:
    | "linear"
    | "easeOut"
    | "easeInOut",
): number => {
  return interpolate(
    frame,
    [start, start + duration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing:
        curve === "linear"
          ? (t) => t
          : curve === "easeOut"
            ? Easing.out(Easing.cubic)
            : Easing.inOut(Easing.cubic),
    },
  );
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<
  counterProps
> = (props) => {
  const frame = useCurrentFrame();

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
        "fonts/Tajawal-Black.ttf",
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

  // ── Counter ────────────────────────────────────────────
  const countProgress = getEasedProgress(
    frame,
    config.revealStart,
    config.countDuration,
    config.curve,
  );

  const currentValue =
    config.value * countProgress;

  const displayNumber = formatNumber(
    currentValue,
    config.numberFormat,
    config.thousandsSeparator,
  );

  const finalDisplayNumber =
    formatNumber(
      config.value,
      config.numberFormat,
      config.thousandsSeparator,
    );

  const isComplete =
    countProgress >= 1;

  // Keep the final formatted value referenced
  // so the completion state remains explicit.
  const renderedNumber =
    isComplete
      ? finalDisplayNumber
      : displayNumber;

  // ── Top label reveal ───────────────────────────────────
  const topLabelOpacity = interpolate(
    frame,
    [20, 45],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const topLabelY = interpolate(
    frame,
    [20, 45],
    [-10, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Number entry ──────────────────────────────────────
  const numberOpacity = interpolate(
    frame,
    [
      config.revealStart - 10,
      config.revealStart + 15,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const numberScale = interpolate(
    frame,
    [
      config.revealStart - 10,
      config.revealStart + 25,
    ],
    [0.9, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Label reveal ──────────────────────────────────────
  const labelOpacity = interpolate(
    frame,
    [
      config.labelDelay,
      config.labelDelay + 25,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const labelY = interpolate(
    frame,
    [
      config.labelDelay,
      config.labelDelay + 25,
    ],
    [12, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Sub-label reveal ───────────────────────────────────
  const subLabelOpacity =
    interpolate(
      frame,
      [
        config.subLabelDelay,
        config.subLabelDelay + 25,
      ],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  const subLabelY = interpolate(
    frame,
    [
      config.subLabelDelay,
      config.subLabelDelay + 25,
    ],
    [8, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Divider draw ───────────────────────────────────────
  const dividerProgress =
    interpolate(
      frame,
      [
        config.labelDelay - 20,
        config.labelDelay + 10,
      ],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  // ── Glow pulse ─────────────────────────────────────────
  const glowDuringCount =
    Math.sin(
      countProgress * Math.PI,
    ) *
      0.5 +
    0.15;

  const settleGlow = isComplete
    ? 0.35
    : glowDuringCount;

  // ── Completion bump ───────────────────────────────────
  const completionBump =
    interpolate(
      frame,
      [
        config.revealStart +
          config.countDuration,
        config.revealStart +
          config.countDuration +
          8,
        config.revealStart +
          config.countDuration +
          22,
      ],
      [1, 1.045, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

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
              "linear-gradient(180deg, rgba(10,46,28,0.55) 0%, rgba(10,46,28,0.3) 40%, rgba(10,46,28,0.65) 100%)",
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

        {/* Content */}
        <AbsoluteFill
          style={{
            direction: "rtl",
            fontFamily:
              "'Tajawal', 'Noto Naskh Arabic', serif",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 140px",
          }}
        >
          {/* Top decorative label */}
          {config.topLabel && (
            <div
              style={{
                fontSize: 26,
                color:
                  config.colors.accent,
                letterSpacing: 8,
                marginBottom: 40,
                opacity:
                  topLabelOpacity,
                transform: `translateY(${topLabelY}px)`,
                textShadow:
                  "0 2px 8px rgba(0,0,0,0.6)",
              }}
            >
              {config.topLabel}
            </div>
          )}

          {/* Big number */}
          <div
            style={{
              position: "relative",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: numberOpacity,
              transform: `scale(${numberScale * completionBump})`,
              transition: "none",
            }}
          >
            {/* Ambient glow */}
            <div
              style={{
                position: "absolute",
                inset: -120,
                background: `radial-gradient(
                  ellipse at center,
                  ${toRgba(
                    config.colors.glow,
                    settleGlow * 0.5,
                  )} 0%,
                  transparent 65%
                )`,
                filter: "blur(40px)",
                pointerEvents:
                  "none",
              }}
            />

            {/* Number row */}
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "center",
                gap: 16,
                direction: "ltr",
              }}
            >
              {/* Prefix */}
              {config.prefix && (
                <span
                  style={{
                    fontSize: 72,
                    color:
                      config.colors.accent,
                    fontWeight: 400,
                    lineHeight: 1,
                    fontFamily:
                      "'Tajawal', 'Noto Naskh Arabic', serif",
                  }}
                >
                  {config.prefix}
                </span>
              )}

              {/* Number */}
              <span
                style={{
                  fontSize: 220,
                  fontWeight: 700,
                  color:
                    config.colors.bright,
                  lineHeight: 1,
                  letterSpacing: -2,
                  fontFamily:
                    "'Tajawal', 'Noto Naskh Arabic', serif",
                  textShadow: `
                    0 4px 24px rgba(0,0,0,0.7),
                    0 0 ${
                      40 * settleGlow
                    }px ${toRgba(
                      config.colors.glow,
                      0.55 * settleGlow,
                    )}
                  `,
                  fontVariantNumeric:
                    "tabular-nums",
                }}
              >
                {renderedNumber}
              </span>

              {/* Suffix */}
              {config.suffix && (
                <span
                  style={{
                    fontSize: 72,
                    color:
                      config.colors.accent,
                    fontWeight: 400,
                    lineHeight: 1,
                    fontFamily:
                      "'Tajawal', 'Noto Naskh Arabic', serif",
                  }}
                >
                  {config.suffix}
                </span>
              )}
            </div>
          </div>

          {/* Decorative divider */}
          <div
            style={{
              position: "relative",
              width: 620,
              height: 1,
              marginTop: 40,
              marginBottom: 32,
              background: `linear-gradient(
                to right,
                transparent 0%,
                ${config.colors.dim} ${
                  50 -
                  dividerProgress * 50
                }%,
                ${config.colors.dim} ${
                  50 +
                  dividerProgress * 50
                }%,
                transparent 100%
              )`,
              opacity: dividerProgress,
            }}
          >
            <div
              style={{
                position: "absolute",
                top: -5,
                left: "50%",
                transform: `translateX(-50%) rotate(45deg) scale(${dividerProgress})`,
                width: 10,
                height: 10,
                backgroundColor:
                  config.colors.accent,
                boxShadow: `0 0 14px ${config.colors.accent}`,
              }}
            />
          </div>

          {/* Main label */}
          <div
            style={{
              fontSize: 34,
              color:
                config.colors.text,
              letterSpacing: 2,
              lineHeight: 1.5,
              textAlign: "center",
              opacity: labelOpacity,
              transform: `translateY(${labelY}px)`,
              maxWidth: 1100,
              textShadow:
                "0 2px 12px rgba(0,0,0,0.7)",
            }}
          >
            {config.label}
          </div>

          {/* Sub-label */}
          {config.subLabel && (
            <div
              style={{
                fontSize: 20,
                color:
                  config.colors.soft,
                letterSpacing: 3,
                marginTop: 18,
                textAlign: "center",
                opacity:
                  subLabelOpacity,
                transform: `translateY(${subLabelY}px)`,
                textShadow:
                  "0 2px 8px rgba(0,0,0,0.6)",
              }}
            >
              {config.subLabel}
            </div>
          )}
        </AbsoluteFill>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Helpers
// =============================================================================

const toRgba = (
  color: string,
  alpha: number,
): string => {
  const match = color.match(
    /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i,
  );

  if (match) {
    return `rgba(${match[1]}, ${match[2]}, ${match[3]}, ${alpha})`;
  }

  return color;
};

// =============================================================================
// Registry exports
// =============================================================================

export const counterDefaults = CONFIG;
export const Counter = MyAnimation;
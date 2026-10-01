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
import { continueRender, delayRender } from "remotion";

// =============================================================================
// ⚙️ CONFIG — default values
// =============================================================================
const CONFIG = {
  // ── Image ──────────────────────────────────────────────
  imageSrc: "images/ken-burns/battle.png",

  // ── Motion ──────────────────────────────────────────────
  motion: "pan-down" as
    | "zoom-in"
    | "zoom-out"
    | "pan-left"
    | "pan-right"
    | "pan-up"
    | "pan-down"
    | "diagonal-tl"
    | "diagonal-tr"
    | "diagonal-bl"
    | "diagonal-br",

  startScale: 1.0,
  endScale: 1.18,
  panAmount: 4,

  // ── Caption ────────────────────────────────────────────
  caption: {
    line1: "مَعْرَكَةُ اليَرْمُوك",
    line2: "١٥ هـ / ٦٣٦ م",
  } as {
    line1: string;
    line2?: string;
  } | null,

  // ── Source ────────────────────────────────────────────
  source: null as string | null,

  // ── Reveal timing ─────────────────────────────────────
  captionRevealStart: 40,
  captionRevealEnd: 70,

  dividerRevealStart: 50,
  dividerRevealEnd: 80,

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 60,
    scale: 1.08,
    rotateX: 8,
  },

  // ── Colors ─────────────────────────────────────────────
  colors: {
    background: "#0a2e1c",
    text: "rgba(240, 222, 165, 0.95)",
    accent: "#e8c874",
    dim: "#8a6f3c",
    soft: "rgba(217, 196, 122, 0.75)",
  },
};

// =============================================================================
// Public props
// =============================================================================

type CaptionConfig = NonNullable<typeof CONFIG.caption>;
type CameraConfig = typeof CONFIG.camera;
type ColorsConfig = typeof CONFIG.colors;

export type kenBurnsProps = Partial<
  Omit<
    typeof CONFIG,
    "caption" | "camera" | "colors"
  >
> & {
  durationInFrames?: number;

  caption?: Partial<CaptionConfig> | null;

  camera?: Partial<CameraConfig>;

  colors?: Partial<ColorsConfig>;
};

// =============================================================================
// Motion presets
// =============================================================================

interface MotionFrame {
  startScale: number;
  endScale: number;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
}

const getMotion = (
  preset: kenBurnsProps["motion"],
  startScale: number,
  endScale: number,
  pan: number,
): MotionFrame => {
  let startX = 0;
  let startY = 0;
  let endX = 0;
  let endY = 0;

  switch (preset) {
    case "zoom-in":
      break;

    case "zoom-out":
      return {
        startScale: endScale,
        endScale: startScale,
        startX: 0,
        startY: 0,
        endX: 0,
        endY: 0,
      };

    case "pan-left":
      startX = pan / 2;
      endX = -pan / 2;
      break;

    case "pan-right":
      startX = -pan / 2;
      endX = pan / 2;
      break;

    case "pan-up":
      startY = pan / 2;
      endY = -pan / 2;
      break;

    case "pan-down":
      startY = -pan / 2;
      endY = pan / 2;
      break;

    case "diagonal-tl":
      startX = pan / 2;
      startY = pan / 2;
      endX = -pan / 2;
      endY = -pan / 2;
      break;

    case "diagonal-tr":
      startX = -pan / 2;
      startY = pan / 2;
      endX = pan / 2;
      endY = -pan / 2;
      break;

    case "diagonal-bl":
      startX = pan / 2;
      startY = -pan / 2;
      endX = -pan / 2;
      endY = pan / 2;
      break;

    case "diagonal-br":
      startX = -pan / 2;
      startY = -pan / 2;
      endX = pan / 2;
      endY = pan / 2;
      break;

    default:
      break;
  }

  return {
    startScale,
    endScale,
    startX,
    startY,
    endX,
    endY,
  };
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<
  kenBurnsProps
> = (props) => {
  const frame = useCurrentFrame();
  const {
    durationInFrames,
  } = useVideoConfig();

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

    // Explicit null must remain null.
    caption:
      props.caption === null
        ? null
        : {
            ...CONFIG.caption,
            ...(props.caption ?? {}),
          },
  };

  // ── Font loading ───────────────────────────────────────
  const [handle] = useState(() =>
    delayRender("Loading Tajawal font"),
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

  // ── Ken Burns motion ───────────────────────────────────
  const motion = getMotion(
    config.motion,
    config.startScale,
    config.endScale,
    config.panAmount,
  );

  const totalFrames = Math.max(
    1,
    durationInFrames,
  );

  const kenProgress = interpolate(
    frame,
    [0, totalFrames - 1],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const kbScale =
    motion.startScale +
    (motion.endScale -
      motion.startScale) *
      kenProgress;

  const kbX =
    motion.startX +
    (motion.endX -
      motion.startX) *
      kenProgress;

  const kbY =
    motion.startY +
    (motion.endY -
      motion.startY) *
      kenProgress;

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

  // ── Caption reveal ─────────────────────────────────────
  const captionOpacity =
    interpolate(
      frame,
      [
        config.captionRevealStart,
        config.captionRevealEnd,
      ],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  const captionY = interpolate(
    frame,
    [
      config.captionRevealStart,
      config.captionRevealEnd,
    ],
    [12, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Divider reveal ─────────────────────────────────────
  const dividerProgress =
    interpolate(
      frame,
      [
        config.dividerRevealStart,
        config.dividerRevealEnd,
      ],
      [0, 1],
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
        perspective: 2000,
        perspectiveOrigin:
          "center center",
      }}
    >
      {/* ===================================================== */}
      {/* Camera rig                                             */}
      {/* ===================================================== */}
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
        {/* =================================================== */}
        {/* Ken Burns image                                     */}
        {/* =================================================== */}
        <div
          style={{
            position: "absolute",
            inset: "-4%",
            transform: `scale(${kbScale}) translate(${kbX}%, ${kbY}%)`,
            transformOrigin:
              "center center",
          }}
        >
          <Img
            src={staticFile(
              config.imageSrc,
            )}
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        </div>

        {/* =================================================== */}
        {/* Palette tint                                        */}
        {/* =================================================== */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `linear-gradient(
              180deg,
              ${config.colors.background === "#0a2e1c"
                ? "rgba(10,46,28,0.55)"
                : `${config.colors.background}8C`} 0%,
              ${config.colors.background === "#0a2e1c"
                ? "rgba(10,46,28,0.15)"
                : `${config.colors.background}26`} 40%,
              ${config.colors.background === "#0a2e1c"
                ? "rgba(10,46,28,0.65)"
                : `${config.colors.background}A6`} 100%
            )`,
            mixBlendMode: "multiply",
            pointerEvents: "none",
          }}
        />

        {/* =================================================== */}
        {/* Warm gold wash                                      */}
        {/* =================================================== */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(
              ellipse at center,
              ${toRgba(
                config.colors.accent,
                0.1,
              )} 0%,
              transparent 65%
            )`,
            mixBlendMode: "screen",
            pointerEvents: "none",
          }}
        />

        {/* =================================================== */}
        {/* Vignette                                             */}
        {/* =================================================== */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.6) 100%)",
            pointerEvents: "none",
          }}
        />

        {/* =================================================== */}
        {/* Optional caption                                    */}
        {/* =================================================== */}
        {config.caption && (
          <div
            style={{
              position: "absolute",
              bottom: "8%",
              left: "50%",
              transform: `translate(-50%, ${captionY}px)`,
              opacity: captionOpacity,
              direction: "rtl",
              textAlign: "center",
              fontFamily:
                "'Tajawal', 'Noto Naskh Arabic', serif",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              pointerEvents: "none",
            }}
          >
            {/* Divider */}
            <div
              style={{
                position:
                  "relative",
                width: 480,
                height: 1,
                background: `linear-gradient(
                  to right,
                  transparent 0%,
                  ${config.colors.dim} ${
                    50 -
                    dividerProgress *
                      50
                  }%,
                  ${config.colors.dim} ${
                    50 +
                    dividerProgress *
                      50
                  }%,
                  transparent 100%
                )`,
                marginBottom: 22,
                opacity:
                  dividerProgress,
              }}
            >
              <div
                style={{
                  position:
                    "absolute",
                  top: -5,
                  left: "50%",
                  transform: `translateX(-50%) rotate(45deg) scale(${dividerProgress})`,
                  width: 10,
                  height: 10,
                  backgroundColor:
                    config.colors
                      .accent,
                  boxShadow: `0 0 14px ${config.colors.accent}`,
                }}
              />
            </div>

            {/* Line 1 */}
            <div
              style={{
                fontSize: 44,
                fontWeight: 700,
                color:
                  config.colors
                    .text,
                letterSpacing: 3,
                lineHeight: 1.3,
                textShadow: `0 4px 18px rgba(0,0,0,0.8), 0 0 40px ${toRgba(
                  config.colors
                    .accent,
                  0.25,
                )}`,
                marginBottom:
                  config.caption
                    .line2
                    ? 10
                    : 0,
              }}
            >
              {config.caption.line1}
            </div>

            {/* Line 2 */}
            {config.caption.line2 && (
              <div
                style={{
                  fontSize: 24,
                  color:
                    config.colors
                      .soft,
                  letterSpacing: 4,
                  textShadow:
                    "0 2px 10px rgba(0,0,0,0.7)",
                }}
              >
                {config.caption.line2}
              </div>
            )}

            {/* Source */}
            {config.source && (
              <div
                style={{
                  marginTop: 18,
                  fontSize: 14,
                  color:
                    config.colors
                      .soft,
                  opacity: 0.6,
                  letterSpacing: 1,
                  fontFamily:
                    "'Tajawal', 'Noto Naskh Arabic', serif",
                }}
              >
                {config.source}
              </div>
            )}
          </div>
        )}
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

  // Hex → rgba
  const hex = color.replace(
    "#",
    "",
  );

  if (
    /^[0-9a-f]{6}$/i.test(
      hex,
    )
  ) {
    const r = parseInt(
      hex.slice(0, 2),
      16,
    );

    const g = parseInt(
      hex.slice(2, 4),
      16,
    );

    const b = parseInt(
      hex.slice(4, 6),
      16,
    );

    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  return color;
};

// =============================================================================
// Registry exports
// =============================================================================

export const kenBurnsDefaults =
  CONFIG;

export const KenBurns =
  MyAnimation;
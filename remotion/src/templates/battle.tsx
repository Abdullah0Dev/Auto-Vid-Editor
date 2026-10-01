import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  interpolate,
  spring,
} from "remotion";
import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

// =============================================================================
// ⚙️ CONFIG — default values
// =============================================================================
const CONFIG = {
  // ── Background ─────────────────────────────────────────
  background: "poem-bg.jpeg",

  // ── Dates (dual calendar) ──────────────────────────────
  hijriDate: "٨٥٧هـ",
  miladiDate: "١٤٥٣م",

  // ── Battle ──────────────────────────────────────────────
  battleName: "فَتْحُ القُسْطَنْطِينِيَّة",

  // ── Two sides ───────────────────────────────────────────
  side1: {
    name: "الدَّوْلَةُ العُثْمَانِيَّة",
    detail: "السُّلْطَان مُحَمَّد الفَاتِح",
  },

  side2: {
    name: "الإِمْبَرَاطُورِيَّةُ البِيزَنْطِيَّة",
    detail: "الإِمْبْرَاطُور قُسْطَنْطِين الحَادِي عَشَر",
  },

  // ── Outcome ────────────────────────────────────────────
  outcome: "نَصْرٌ عُثْمَانِيٌّ حَاسِمٌ",

  // ── Source ─────────────────────────────────────────────
  source: "المَصْدَر: تَارِيخُ الدَّوْلَةِ العُثْمَانِيَّة",

  // ── Timing ─────────────────────────────────────────────
  fps: 30,

  timing: {
    dateIn: 20,
    titleIn: 55,
    dividerIn: 115,
    sidesIn: 130,
    outcomeIn: 190,
    sourceIn: 220,
    titleSweepDuration: 45,
  },

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 70,
    scale: 1.15,
    rotateX: 10,
  },

  // ── Colors ─────────────────────────────────────────────
  colors: {
    text: "rgba(240, 222, 165, 0.95)",
    accent: "#e8c874",
    dim: "#8a6f3c",
    soft: "rgba(217, 196, 122, 0.7)",
    highlightRgb: "217, 170, 60",
    sideOne: "#f0dea5",
    sideTwo: "rgba(200, 180, 140, 0.7)",
    background: "#0a2e1c",
  },
};

// =============================================================================
// Public props
// =============================================================================

type SideConfig = typeof CONFIG.side1;
type CameraConfig = typeof CONFIG.camera;
type TimingConfig = typeof CONFIG.timing;
type ColorsConfig = typeof CONFIG.colors;

export type battleProps = Partial<
  Omit<
    typeof CONFIG,
    "side1" | "side2" | "camera" | "timing" | "colors"
  >
> & {
  durationInFrames?: number;

  side1?: Partial<SideConfig>;
  side2?: Partial<SideConfig>;
  camera?: Partial<CameraConfig>;
  timing?: Partial<TimingConfig>;
  colors?: Partial<ColorsConfig>;
};

// =============================================================================
// Decorative — crossed saifs (Arabic curved swords)
// =============================================================================

const CrossedSaifs = ({
  size = 140,
  color = "#e8c874",
  opacity = 0.9,
}: {
  size?: number;
  color?: string;
  opacity?: number;
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    opacity={opacity}
  >
    {/* Blade 1: bottom-left to top-right */}
    <path
      d="M 15 90 Q 50 50 88 12"
      stroke={color}
      strokeWidth="2.5"
      strokeLinecap="round"
      fill="none"
    />

    {/* Blade 2: top-left to bottom-right */}
    <path
      d="M 12 12 Q 50 50 85 90"
      stroke={color}
      strokeWidth="2.5"
      strokeLinecap="round"
      fill="none"
    />

    {/* Hilts */}
    <circle
      cx="18"
      cy="87"
      r="3"
      fill={color}
    />

    <circle
      cx="15"
      cy="15"
      r="3"
      fill={color}
    />
  </svg>
);

// =============================================================================
// Battle side
// =============================================================================

const BattleSide = ({
  name,
  detail,
  delay,
  align,
  color,
  fps,
  detailColor,
}: {
  name: string;
  detail: string;
  delay: number;
  align: "right" | "left";
  color: string;
  fps: number;
  detailColor: string;
}) => {
  const frame = useCurrentFrame();

  const p = spring({
    frame: frame - delay,
    fps,
    config: {
      damping: 16,
      stiffness: 90,
    },
  });

  const translateX = interpolate(
    p,
    [0, 1],
    [
      align === "right" ? 40 : -40,
      0,
    ],
  );

  const opacity = interpolate(
    p,
    [0, 1],
    [0, 1],
  );

  return (
    <div
      style={{
        transform: `translateX(${translateX}px)`,
        opacity,
        textAlign: "center",
        flex: 1,
      }}
    >
      <div
        style={{
          fontSize: 26,
          color,
          fontFamily:
            "'Tajawal', 'Noto Naskh Arabic', serif",
          fontWeight: 600,
          marginBottom: 8,
          lineHeight: 1.35,
        }}
      >
        {name}
      </div>

      <div
        style={{
          fontSize: 18,
          color: detailColor,
          fontFamily:
            "'Tajawal', 'Noto Naskh Arabic', serif",
          lineHeight: 1.4,
        }}
      >
        {detail}
      </div>
    </div>
  );
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<battleProps> = (
  props,
) => {
  const frame = useCurrentFrame();

  // ── Merge defaults + runtime props ──────────────────────
  const config = {
    ...CONFIG,
    ...props,

    side1: {
      ...CONFIG.side1,
      ...(props.side1 ?? {}),
    },

    side2: {
      ...CONFIG.side2,
      ...(props.side2 ?? {}),
    },

    camera: {
      ...CONFIG.camera,
      ...(props.camera ?? {}),
    },

    timing: {
      ...CONFIG.timing,
      ...(props.timing ?? {}),
    },

    colors: {
      ...CONFIG.colors,
      ...(props.colors ?? {}),
    },
  };

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

  // ── Timing ─────────────────────────────────────────────
  const {
    dateIn,
    titleIn,
    dividerIn,
    sidesIn,
    outcomeIn,
    sourceIn,
    titleSweepDuration,
  } = config.timing;

  // ── Date fade ──────────────────────────────────────────
  const dateOpacity = interpolate(
    frame,
    [dateIn, dateIn + 30],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const dateY = interpolate(
    frame,
    [dateIn, dateIn + 30],
    [-12, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Title sweep ────────────────────────────────────────
  const titleSweep = interpolate(
    frame - titleIn,
    [0, titleSweepDuration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const titleBgImage = `linear-gradient(
    to left,
    rgba(${config.colors.highlightRgb}, 0.5) 50%,
    transparent 50%
  )`;

  // ── Ambient glow pulse ─────────────────────────────────
  const glowPulse =
    0.7 +
    0.15 *
      Math.sin(
        (frame / config.fps) * 0.8,
      ) *
      interpolate(
        frame,
        [titleIn, titleIn + 30],
        [0, 1],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        },
      );

  // ── Divider draw ────────────────────────────────────────
  const dividerProgress = interpolate(
    frame - dividerIn,
    [0, 30],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // ── Sides ───────────────────────────────────────────────
  const sideOneDelay = sidesIn;
  const sideTwoDelay = sidesIn + 12;

  // ── Crossed saifs ──────────────────────────────────────
  const saifProgress = spring({
    frame: frame - sidesIn + 20,
    fps: config.fps,
    config: {
      damping: 14,
      stiffness: 80,
    },
  });

  // ── Outcome ─────────────────────────────────────────────
  const outcomeP = interpolate(
    frame - outcomeIn,
    [0, 30],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const outcomeY = interpolate(
    outcomeP,
    [0, 1],
    [18, 0],
  );

  // ── Source ──────────────────────────────────────────────
  const sourceP = interpolate(
    frame - sourceIn,
    [0, 25],
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

        {/* Green tint */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(180deg, rgba(10,46,28,0.55) 0%, rgba(10,46,28,0.25) 40%, rgba(10,46,28,0.65) 100%)",
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

        {/* ===================================================== */}
        {/* Dual-calendar date                                     */}
        {/* ===================================================== */}
        <div
          style={{
            position: "absolute",
            top: "10%",
            left: "50%",
            transform: `translate(-50%, ${dateY}px)`,
            opacity: dateOpacity,
            direction: "rtl",
            fontFamily:
              "'Tajawal', 'Noto Naskh Arabic', serif",
            color: config.colors.accent,
            fontSize: 22,
            letterSpacing: 4,
            textShadow:
              "0 2px 10px rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            gap: 18,
          }}
        >
          <span>{config.hijriDate}</span>

          <span
            style={{
              color: config.colors.dim,
              fontSize: 16,
            }}
          >
            ◆
          </span>

          <span>{config.miladiDate}</span>
        </div>

        {/* ===================================================== */}
        {/* Center content                                         */}
        {/* ===================================================== */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            direction: "rtl",
            fontFamily:
              "'Tajawal', 'Noto Naskh Arabic', serif",
            padding: "0 8%",
          }}
        >
          {/* Ambient glow */}
          <div
            style={{
              position: "absolute",
              width: 900,
              height: 260,
              top: "calc(50% - 220px)",
              left: "50%",
              transform:
                "translate(-50%, -50%)",
              background: `radial-gradient(
                ellipse,
                rgba(232, 200, 116, ${
                  0.22 * glowPulse
                }) 0%,
                transparent 70%
              )`,
              filter: "blur(20px)",
              pointerEvents: "none",
            }}
          />

          {/* Faint crossed saifs watermark */}
          <div
            style={{
              position: "absolute",
              top: "calc(50% - 200px)",
              left: "50%",
              transform:
                "translate(-50%, -50%)",
              opacity: 0.08,
              pointerEvents: "none",
            }}
          >
            <CrossedSaifs
              size={240}
              color={config.colors.accent}
            />
          </div>

          {/* Battle name */}
          <div
            style={{
              position: "relative",
              fontSize: 78,
              fontWeight: 700,
              lineHeight: 1.25,
              marginBottom: 44,
              color: config.colors.text,
              letterSpacing: 2,
              textShadow:
                "0 4px 18px rgba(0,0,0,0.75), 0 0 40px rgba(232, 200, 116, 0.25)",
              textAlign: "center",
            }}
          >
            <span
              style={{
                display: "inline",
                backgroundImage:
                  titleBgImage,
                backgroundSize: "200% 100%",
                backgroundPosition: `${titleSweep * 100}% 0`,
                backgroundRepeat: "no-repeat",
                boxDecorationBreak: "clone",
                WebkitBoxDecorationBreak:
                  "clone",
                padding: "0.05em 0.2em",
                borderRadius: 6,
              }}
            >
              {config.battleName}
            </span>
          </div>

          {/* Decorative divider */}
          <div
            style={{
              position: "relative",
              width: 640,
              height: 1,
              marginBottom: 60,
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
                top: -6,
                left: "50%",
                transform: `translateX(-50%) rotate(45deg) scale(${dividerProgress})`,
                width: 12,
                height: 12,
                backgroundColor:
                  config.colors.accent,
                boxShadow: `0 0 12px ${config.colors.accent}`,
              }}
            />
          </div>

          {/* Two sides */}
          <div
            style={{
              display: "flex",
              flexDirection: "row",
              alignItems: "center",
              justifyContent:
                "space-between",
              width: "100%",
              maxWidth: 1100,
              marginBottom: 70,
              gap: 24,
            }}
          >
            {/* Side 1 */}
            <BattleSide
              name={config.side1.name}
              detail={config.side1.detail}
              delay={sideOneDelay}
              align="right"
              color={config.colors.sideOne}
              detailColor={
                config.colors.soft
              }
              fps={config.fps}
            />

            {/* Crossed saifs */}
            <div
              style={{
                transform: `scale(${saifProgress}) rotate(${interpolate(
                  saifProgress,
                  [0, 1],
                  [-15, 0],
                )}deg)`,
                opacity: saifProgress,
                flexShrink: 0,
              }}
            >
              <CrossedSaifs
                size={70}
                color={config.colors.accent}
                opacity={1}
              />
            </div>

            {/* Side 2 */}
            <BattleSide
              name={config.side2.name}
              detail={config.side2.detail}
              delay={sideTwoDelay}
              align="left"
              color={config.colors.sideTwo}
              detailColor={
                config.colors.soft
              }
              fps={config.fps}
            />
          </div>

          {/* Outcome */}
          <div
            style={{
              transform: `translateY(${outcomeY}px)`,
              opacity: outcomeP,
              fontSize: 34,
              color: config.colors.accent,
              fontWeight: 600,
              letterSpacing: 3,
              textShadow: `0 0 20px rgba(232, 200, 116, ${
                0.35 * outcomeP
              }), 0 2px 10px rgba(0,0,0,0.7)`,
              textAlign: "center",
            }}
          >
            {config.outcome}
          </div>
        </div>

        {/* ===================================================== */}
        {/* Source                                                  */}
        {/* ===================================================== */}
        <div
          style={{
            position: "absolute",
            bottom: "6%",
            left: "50%",
            transform:
              "translateX(-50%)",
            opacity: sourceP,
            direction: "rtl",
            fontFamily:
              "'Tajawal', 'Noto Naskh Arabic', serif",
            color: config.colors.soft,
            fontSize: 16,
            letterSpacing: 1,
            textShadow:
              "0 2px 8px rgba(0,0,0,0.7)",
          }}
        >
          {config.source}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Registry exports
// =============================================================================

export const battleDefaults = CONFIG;
export const Battle = MyAnimation;

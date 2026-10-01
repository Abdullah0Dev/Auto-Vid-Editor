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
  portraitSrc: null as string | null,
  name: "عُمَرُ بْنُ الخَطَّاب",
  honorific: "رَضِيَ اللَّهُ عَنْهُ",
  title: "الفَارُوقُ أَمِيرُ المُؤْمِنِينَ",
  birthYear: "٤٠ ق.هـ",
  deathYear: "٢٣هـ",
  birthPlace: "مَكَّة",
  deathPlace: "المَدِينَة",
  footerLabel: "الخُلَفَاءُ الرَّاشِدُونَ",

  // ── Timing ─────────────────────────────────────────────
  timing: {
    portrait: 25,
    name: 40,
    honorific: 100,
    title: 130,
    divider: 200,
    dates: 215,
    places: 245,
    footer: 260,
    nameWordDuration: 12,
    titleWordDuration: 10,
  },

  // ── Layout ─────────────────────────────────────────────
  layout: {
    nameSize: 54,
    honorificSize: 28,
    titleSize: 38,
    metaSize: 26,
    lineHeight: 1.4,
    portraitWidth: 380,
    portraitHeight: 460,
    contentGap: 60,
  },

  // ── Camera ─────────────────────────────────────────────
  camera: {
    startFrame: 10,
    endFrame: 60,
    scale: 1.13,
    rotateX: 12,
  },

  // ── Colors ─────────────────────────────────────────────
  colors: {
    text: "rgba(217, 196, 122, 0.75)",
    accent: "#b8935a",
    dim: "#8a6f3c",
    bright: "#f5e5a8",
    highlightRgb: "217, 170, 60",
    background: "#0a2e1c",
    glow: "#e8c874",
  },

  // ── Assets ─────────────────────────────────────────────
  font: {
    primary: "fonts/Tajawal-Medium.ttf",
    decorative: "fonts/ArefRuqaa-Bold.ttf",
  },
};

// =============================================================================
// Public props
// =============================================================================

type TimingConfig = typeof CONFIG.timing;
type LayoutConfig = typeof CONFIG.layout;
type CameraConfig = typeof CONFIG.camera;
type ColorsConfig = typeof CONFIG.colors;
type FontConfig = typeof CONFIG.font;

export type personCardProps = Partial<
  Omit<
    typeof CONFIG,
    "timing" | "layout" | "camera" | "colors" | "font"
  >
> & {
  durationInFrames?: number;

  timing?: Partial<TimingConfig>;
  layout?: Partial<LayoutConfig>;
  camera?: Partial<CameraConfig>;
  colors?: Partial<ColorsConfig>;
  font?: Partial<FontConfig>;
};

// =============================================================================
// Word sweep
// =============================================================================

const WordSweep = ({
  text,
  delay,
  duration,
  color,
  highlightRgb,
}: {
  text: string;
  delay: number;
  duration: number;
  color: string;
  highlightRgb: string;
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
        color,
      }}
    >
      {text}
    </span>
  );
};

// =============================================================================
// Word helper
// =============================================================================

const toWords = (text: string): string[] =>
  text.trim().split(/\s+/).map((word, i, arr) =>
    i < arr.length - 1 ? word + " " : word,
  );

// =============================================================================
// Portrait
// =============================================================================

const Portrait = ({
  delay,
  portraitSrc,
  name,
  portraitWidth,
  portraitHeight,
  colors,
}: {
  delay: number;
  portraitSrc: string | null;
  name: string;
  portraitWidth: number;
  portraitHeight: number;
  colors: ColorsConfig;
}) => {
  const frame = useCurrentFrame();

  const progress = interpolate(
    frame - delay,
    [0, 35],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const scale = interpolate(
    progress,
    [0, 1],
    [0.92, 1],
  );

  return (
    <div
      style={{
        position: "relative",
        width: portraitWidth,
        height: portraitHeight,
        flexShrink: 0,
        opacity: progress,
        transform: `scale(${scale})`,
      }}
    >
      {/* Soft gold glow */}
      <div
        style={{
          position: "absolute",
          inset: -40,
          background: `radial-gradient(
            ellipse at center,
            ${toRgba(colors.glow, 0.22)} 0%,
            transparent 70%
          )`,
          filter: "blur(20px)",
          pointerEvents: "none",
        }}
      />

      {/* Portrait frame */}
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          border: `2px solid ${colors.accent}`,
          borderRadius: 6,
          overflow: "hidden",
          backgroundColor:
            colors.background,
          boxShadow: `
            0 0 30px ${toRgba(colors.glow, 0.25)},
            0 8px 24px rgba(0,0,0,0.6)
          `,
        }}
      >
        {portraitSrc ? (
          <Img
            src={staticFile(portraitSrc)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        ) : (
          // Fallback monogram
          <div
            style={{
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: `linear-gradient(
                135deg,
                ${colors.background} 0%,
                ${lightenColor(colors.background, 0.08)} 100%
              )`,
            }}
          >
            <div
              style={{
                width: 160,
                height: 160,
                borderRadius: "50%",
                border: `3px solid ${colors.accent}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 96,
                fontFamily:
                  "'ArefRuqaa', 'Noto Naskh Arabic', serif",
                color: colors.bright,
                boxShadow: `0 0 40px ${toRgba(
                  colors.glow,
                  0.4,
                )} inset`,
              }}
            >
              {name.charAt(0)}
            </div>
          </div>
        )}

        {/* Portrait vignette */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(
              ellipse at center,
              transparent 55%,
              ${toRgba(colors.background, 0.5)} 100%
            )`,
            pointerEvents: "none",
          }}
        />
      </div>

      {/* Corner ornaments */}
      {[
        { top: -6, left: -6, rotate: 0 },
        { top: -6, right: -6, rotate: 90 },
        { bottom: -6, right: -6, rotate: 180 },
        { bottom: -6, left: -6, rotate: 270 },
      ].map((pos, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            width: 20,
            height: 20,
            borderTop: `2px solid ${colors.bright}`,
            borderLeft: `2px solid ${colors.bright}`,
            transform: `rotate(${pos.rotate}deg)`,
            transformOrigin: "center",
            ...pos,
          }}
        />
      ))}
    </div>
  );
};

// =============================================================================
// Info fade
// =============================================================================

const InfoFade = ({
  children,
  delay,
  color,
  fontSize,
  letterSpacing,
  lineHeight,
}: {
  children: React.ReactNode;
  delay: number;
  color: string;
  fontSize: number;
  letterSpacing: number;
  lineHeight: number;
}) => {
  const frame = useCurrentFrame();

  const progress = interpolate(
    frame - delay,
    [0, 25],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const y = interpolate(
    progress,
    [0, 1],
    [10, 0],
  );

  return (
    <div
      style={{
        opacity: progress,
        transform: `translateY(${y}px)`,
        color,
        fontSize,
        letterSpacing,
        lineHeight,
      }}
    >
      {children}
    </div>
  );
};

// =============================================================================
// Main
// =============================================================================

export const MyAnimation: React.FC<
  personCardProps
> = (props) => {
  const frame = useCurrentFrame();

  // ── Merge defaults + runtime props ──────────────────────
  const config = {
    ...CONFIG,
    ...props,

    timing: {
      ...CONFIG.timing,
      ...(props.timing ?? {}),
    },

    layout: {
      ...CONFIG.layout,
      ...(props.layout ?? {}),
    },

    camera: {
      ...CONFIG.camera,
      ...(props.camera ?? {}),
    },

    colors: {
      ...CONFIG.colors,
      ...(props.colors ?? {}),
    },

    font: {
      ...CONFIG.font,
      ...(props.font ?? {}),
    },
  };

  // ── Font loading ───────────────────────────────────────
  const [handle] = useState(() =>
    delayRender(
      "Loading person card fonts",
    ),
  );

  useEffect(() => {
    const loadFont = async (
      family: string,
      path: string,
    ) => {
      try {
        const font = new FontFace(
          family,
          `url(${staticFile(path)})`,
        );

        await font.load();
        document.fonts.add(font);
      } catch (err) {
        console.error(
          `${family} font load failed`,
          err,
        );
      }
    };

    Promise.all([
      loadFont(
        "Tajawal",
        config.font.primary,
      ),
      loadFont(
        "ArefRuqaa",
        config.font.decorative,
      ),
    ]).finally(() => {
      continueRender(handle);
    });
  }, [
    handle,
    config.font.primary,
    config.font.decorative,
  ]);

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

  // ── Words ──────────────────────────────────────────────
  const nameWords = toWords(
    config.name,
  );

  const titleWords = toWords(
    config.title,
  );

  // ── Divider ────────────────────────────────────────────
  const dividerProgress =
    interpolate(
      frame - config.timing.divider,
      [0, 30],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      },
    );

  // ── Footer opacity ─────────────────────────────────────
  const footerDividerOpacity =
    interpolate(
      frame - config.timing.footer,
      [0, 20],
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
        perspective: 1800,
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
        {/* Background */}
        <Img
          src={staticFile(
            config.background ??
              "poem-bg.jpeg",
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
            background: `linear-gradient(
              180deg,
              ${toRgba(
                config.colors.background,
                0.5,
              )} 0%,
              ${toRgba(
                config.colors.background,
                0.2,
              )} 40%,
              ${toRgba(
                config.colors.background,
                0.6,
              )} 100%
            )`,
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

        {/* =================================================== */}
        {/* Content                                              */}
        {/* =================================================== */}
        <AbsoluteFill
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 140px",
            gap: config.layout.contentGap,
          }}
        >
          {/* Portrait */}
          <Portrait
            delay={config.timing.portrait}
            portraitSrc={
              config.portraitSrc
            }
            name={config.name}
            portraitWidth={
              config.layout.portraitWidth
            }
            portraitHeight={
              config.layout.portraitHeight
            }
            colors={config.colors}
          />

          {/* Text block */}
          <div
            style={{
              direction: "rtl",
              textAlign: "right",
              fontFamily:
                "'Tajawal', 'Noto Naskh Arabic', 'Amiri', serif",
              maxWidth: 780,
              flex: 1,
            }}
          >
            {/* Name */}
            <div
              style={{
                fontSize:
                  config.layout.nameSize,
                fontWeight: 700,
                lineHeight: 1.3,
                color:
                  config.colors.bright,
                marginBottom: 8,
                textShadow:
                  "0 2px 12px rgba(0,0,0,0.6)",
              }}
            >
              {nameWords.map(
                (word, i) => (
                  <WordSweep
                    key={i}
                    text={word}
                    delay={
                      config.timing
                        .name +
                      i *
                        config.timing
                          .nameWordDuration
                    }
                    duration={
                      config.timing
                        .nameWordDuration *
                      2
                    }
                    color={
                      config.colors.bright
                    }
                    highlightRgb={
                      config.colors.highlightRgb
                    }
                  />
                ),
              )}
            </div>

            {/* Honorific */}
            <InfoFade
              delay={
                config.timing.honorific
              }
              color={
                config.colors.accent
              }
              fontSize={
                config.layout
                  .honorificSize
              }
              letterSpacing={2}
              lineHeight={
                config.layout.lineHeight
              }
            >
              {config.honorific}
            </InfoFade>

            {/* Title */}
            <div
              style={{
                fontSize:
                  config.layout.titleSize,
                lineHeight: 1.4,
                color:
                  config.colors.text,
                marginTop: 26,
                marginBottom: 30,
                letterSpacing: 1,
              }}
            >
              {titleWords.map(
                (word, i) => (
                  <WordSweep
                    key={i}
                    text={word}
                    delay={
                      config.timing.title +
                      i *
                        config.timing
                          .titleWordDuration
                    }
                    duration={
                      config.timing
                        .titleWordDuration *
                      2
                    }
                    color={
                      config.colors.text
                    }
                    highlightRgb={
                      config.colors.highlightRgb
                    }
                  />
                ),
              )}
            </div>

            {/* Divider */}
            <div
              style={{
                position:
                  "relative",
                width: 320,
                height: 1,
                marginBottom: 26,
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
                    config.colors.accent,
                  boxShadow: `0 0 12px ${config.colors.accent}`,
                }}
              />
            </div>

            {/* Dates */}
            <InfoFade
              delay={
                config.timing.dates
              }
              color={
                config.colors.text
              }
              fontSize={
                config.layout.metaSize
              }
              letterSpacing={1}
              lineHeight={
                config.layout.lineHeight
              }
            >
              {config.birthYear}
              {" "}
              <span
                style={{
                  color:
                    config.colors.dim,
                }}
              >
                —
              </span>
              {" "}
              {config.deathYear}
            </InfoFade>

            {/* Places */}
            <div
              style={{
                marginTop: 10,
              }}
            >
              <InfoFade
                delay={
                  config.timing.places
                }
                color={
                  config.colors.accent
                }
                fontSize={
                  22
                }
                letterSpacing={1}
                lineHeight={
                  config.layout
                    .lineHeight
                }
              >
                {config.birthPlace}
                {" "}
                <span
                  style={{
                    color:
                      config.colors.dim,
                  }}
                >
                  ←
                </span>
                {" "}
                {config.deathPlace}
              </InfoFade>
            </div>
          </div>
        </AbsoluteFill>

        {/* =================================================== */}
        {/* Footer                                               */}
        {/* =================================================== */}
        <div
          style={{
            position: "absolute",
            bottom: "7%",
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
              position:
                "relative",
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
              opacity:
                footerDividerOpacity,
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

          <InfoFade
            delay={
              config.timing.footer
            }
            color={
              config.colors.text
            }
            fontSize={20}
            letterSpacing={4}
            lineHeight={
              config.layout
                .lineHeight
            }
          >
            {config.footerLabel}
          </InfoFade>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// =============================================================================
// Helpers
// =============================================================================

const parseColor = (
  color: string,
): {
  r: number;
  g: number;
  b: number;
  a: number;
} | null => {
  const rgbaMatch =
    color.match(
      /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)$/i,
    );

  if (rgbaMatch) {
    return {
      r: Number(rgbaMatch[1]),
      g: Number(rgbaMatch[2]),
      b: Number(rgbaMatch[3]),
      a:
        rgbaMatch[4] !== undefined
          ? Number(rgbaMatch[4])
          : 1,
    };
  }

  const hex = color.replace(
    "#",
    "",
  );

  if (
    /^[0-9a-f]{6}$/i.test(
      hex,
    )
  ) {
    return {
      r: parseInt(
        hex.slice(0, 2),
        16,
      ),
      g: parseInt(
        hex.slice(2, 4),
        16,
      ),
      b: parseInt(
        hex.slice(4, 6),
        16,
      ),
      a: 1,
    };
  }

  return null;
};

const toRgba = (
  color: string,
  alpha: number,
): string => {
  const parsed = parseColor(
    color,
  );

  if (!parsed) {
    return color;
  }

  return `rgba(
    ${parsed.r},
    ${parsed.g},
    ${parsed.b},
    ${alpha}
  )`;
};

const lightenColor = (
  color: string,
  amount: number,
): string => {
  const parsed = parseColor(
    color,
  );

  if (!parsed) {
    return color;
  }

  const r = Math.min(
    255,
    Math.round(
      parsed.r +
        (255 - parsed.r) *
          amount,
    ),
  );

  const g = Math.min(
    255,
    Math.round(
      parsed.g +
        (255 - parsed.g) *
          amount,
    ),
  );

  const b = Math.min(
    255,
    Math.round(
      parsed.b +
        (255 - parsed.b) *
          amount,
    ),
  );

  return `rgb(${r}, ${g}, ${b})`;
};

// =============================================================================
// Registry exports
// =============================================================================

export const personCardDefaults =
  CONFIG;

export const PersonCard =
  MyAnimation;
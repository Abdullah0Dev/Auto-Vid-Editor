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
// ⚙️ CONFIG — everything you'd want to tune
// =============================================================================
// =============================================================================
// STATIC CITY CATALOG — intentionally NOT configurable at render time.
// Python may reference these IDs for spotlight/journey, but cannot replace
// or mutate the city list/coordinates.
// =============================================================================
const MAP_CITIES = [
  // --- Iberia & Maghreb (west) ---
  { id: "cordoba",     name: "قُرْطُبَة",           x: 3.3,  y: 35.6, year: "٩٢هـ",  icon: "star"   as const },
  { id: "seville",     name: "إِشْبِيلِيَة",         x: 3.8,  y: 40.5,              icon: "city"   as const },
  { id: "fez",         name: "فَاس",                 x: 11.5, y: 31.5, year: "١٩٣هـ", icon: "city"   as const },
  { id: "marrakesh",   name: "مَرَّاكُش",            x: 7.0,  y: 39.0, year: "٤٦٣هـ", icon: "star"   as const },
  { id: "kairouan",    name: "القَيْرَوَان",         x: 30.0, y: 42.0, year: "٥٠هـ",  icon: "mosque" as const },

  // --- Egypt ---
  { id: "alexandria",  name: "الإِسْكَنْدَرِيَّة",    x: 40.5, y: 47.0,              icon: "city"   as const },
  { id: "cairo",       name: "القَاهِرَة",           x: 44.0, y: 52.0, year: "٣٥٨هـ", icon: "star"   as const },
  { id: "tripoli",     name: "طَرَابُلُس الغَرْب",    x: 26.0, y: 48.4, year: "٢٣هـ",  icon: "city"   as const },

  // --- Levant ---
  { id: "aleppo",      name: "حَلَب",                x: 58.0, y: 38.0,              icon: "city"   as const },
  { id: "damascus",    name: "دِمَشْق",              x: 57.0, y: 43.6, year: "١٤هـ",  icon: "star"   as const },
  { id: "jerusalem",   name: "بَيْتُ المَقْدِس",      x: 54.8, y: 50.2, year: "١٧هـ",  icon: "mosque" as const },

  // --- Iraq & Persia ---
  { id: "mosul",       name: "المَوْصِل",            x: 63.5, y: 37.5,              icon: "city"   as const },
  { id: "baghdad",     name: "بَغْدَاد",             x: 68.3, y: 41.1, year: "١٤٥هـ", icon: "star"   as const },
  { id: "kufa",        name: "الكُوفَة",             x: 66.5, y: 45.5, year: "١٧هـ",  icon: "city"   as const },
  { id: "basra",       name: "البَصْرَة",            x: 70.0, y: 52.0, year: "١٤هـ",  icon: "city"   as const },
  { id: "isfahan",     name: "أَصْبَهَان",           x: 76.5, y: 40.0,              icon: "city"   as const },
  { id: "nishapur",    name: "نَيْسَابُور",          x: 81.5, y: 27.0,              icon: "city"   as const },

  // --- Central Asia ---
  { id: "bukhara",     name: "بُخَارَى",             x: 85.5, y: 22.0, year: "٢٣٦هـ", icon: "mosque" as const },
  { id: "samarkand",   name: "سَمَرْقَنْد",          x: 88.5, y: 25.5,              icon: "star"   as const },

  // --- Arabia ---
  { id: "medina",      name: "المَدِينَةُ المُنَوَّرَة", x: 61.9, y: 67.7,          icon: "mosque" as const },
  { id: "mecca",       name: "مَكَّة المُكَرَّمَة",   x: 64.5, y: 77.5,              icon: "kaaba"  as const },
  { id: "sanaa",       name: "صَنْعَاء",             x: 67.5, y: 80.0,              icon: "city"   as const },

  // --- Far west (Europe) ---
  { id: "poitiers",    name: "بُوَاطِيَة",           x: 8.5,  y: 11.2, year: "١١٤هـ", icon: "battle" as const },
  { id: "constantinople", name: "القُسْطَنْطِينِيَّة", x: 49.5, y: 22.0, year: "٨٥٧هـ", icon: "star" as const },
]
const CONFIG = {
  // -------------------------------------------------------------
  // OPTIONAL SPOTLIGHT — highlight one city. Set to `null` to disable.
  // -------------------------------------------------------------
  // Example: "the person we're talking about was in Baghdad"
  spotlight: {
    cityId: "baghdad",
    startFrame: 60,       // when the spotlight begins (30 = 1s)
    label: "هُنَا كَانَ",  // text shown under the city name
  } as { cityId: string; startFrame: number; label?: string } | null,

  // -------------------------------------------------------------
  // OPTIONAL JOURNEY — draw a route connecting cities in order.
  // Set to `null` to disable.
  // -------------------------------------------------------------
  // Example: "he traveled from Mecca → Medina → Damascus"
  journey: {
    path: ["mecca", "medina", "damascus", "baghdad"],
    startFrame: 60,
    drawDuration: 90,     // frames to draw the whole line
    color: "rgba(232, 200, 116, 0.9)",
    label: "رِحْلَةُ العِلْم",
  } as {
    path: string[];
    startFrame: number;
    drawDuration: number;
    color: string;
    label?: string;
  } | null,

  // Title
  title: "دِيَارُ الإِسْلَام",
  subtitle: "في العصر الأموي",
  footer: "فُتُوحَاتُ الإِسْلَام",

  // Camera
  camera: {
    startFrame: 10,
    endFrame: 70,
    scale: 1.18,
    rotateX: 10,
  },
};

// --- Colors ---
const GOLD_TEXT = "rgba(245, 230, 175, 0.95)";
const GOLD_ACCENT = "#e8c874";
const GOLD_DIM = "#8a6f3c";
const PIN_COLOR = "#f5e5a8";
const PIN_GLOW = "rgba(232, 200, 116, 0.55)";
const SPOTLIGHT_GLOW = "rgba(255, 220, 130, 0.95)";

// =============================================================================
// SVG icons
// =============================================================================
const KaabaIcon = ({ size = 32, color = PIN_COLOR }: { size?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
    <rect x="8" y="10" width="16" height="16" fill={color} />
    <rect x="8" y="14" width="16" height="2" fill="#0a2e1c" />
    <rect x="14" y="10" width="4" height="6" fill="#0a2e1c" opacity="0.55" />
  </svg>
);

const MosqueIcon = ({ size = 32, color = PIN_COLOR }: { size?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
    <path d="M6 22 Q6 12 16 12 Q26 12 26 22 Z" fill={color} />
    <rect x="4" y="22" width="24" height="2" fill={color} />
    <rect x="22" y="8" width="2" height="14" fill={color} />
    <circle cx="23" cy="7" r="1.5" fill={color} />
  </svg>
);

const CityIcon = ({ size = 28, color = PIN_COLOR }: { size?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 28 28" fill="none">
    <rect x="4" y="14" width="6" height="10" fill={color} />
    <rect x="11" y="10" width="6" height="14" fill={color} />
    <rect x="18" y="16" width="6" height="8" fill={color} />
    <circle cx="14" cy="7" r="2" fill={color} />
  </svg>
);

const StarIcon = ({ size = 30, color = PIN_COLOR }: { size?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 30 30" fill="none">
    <path
      d="M15 2 L17.5 10 L25 6 L21 13.5 L29 15 L21 16.5 L25 24 L17.5 20 L15 28 L12.5 20 L5 24 L9 16.5 L1 15 L9 13.5 L5 6 L12.5 10 Z"
      fill={color}
    />
  </svg>
);

const BattleIcon = ({ size = 30, color = PIN_COLOR }: { size?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 30 30" fill="none">
    <line x1="6" y1="6" x2="24" y2="24" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
    <line x1="24" y1="6" x2="6" y2="24" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

const ICONS = {
  kaaba: KaabaIcon,
  mosque: MosqueIcon,
  city: CityIcon,
  star: StarIcon,
  battle: BattleIcon,
};

// =============================================================================
// City pin — appears once, stays. Optional spotlight toggles a glow + label.
// =============================================================================
interface City {
  id: string;
  name: string;
  x: number;
  y: number;
  year?: string;
  icon: "kaaba" | "mosque" | "star" | "city" | "battle";
}

const CityPin = ({
  city,
  entryDelay,
  isSpotlighted,
  spotlightDelay,
  spotlightLabel,
}: {
  city: City;
  entryDelay: number;
  isSpotlighted: boolean;
  spotlightDelay: number;
  spotlightLabel?: string;
}) => {
  const frame = useCurrentFrame();

  // Entry: all pins pop in together, quickly, staggered by index
  const enterProgress = spring({
    frame: frame - entryDelay,
    fps: 30,
    config: { damping: 14, stiffness: 150 },
  });
  const enterScale = interpolate(enterProgress, [0, 1], [0, 1]);
  const enterOpacity = interpolate(enterProgress, [0, 1], [0, 1]);

  // Spotlight: pulse glow + slide-in tag when this city is activated
  const spotlightProgress = isSpotlighted
    ? interpolate(frame - spotlightDelay, [0, 25], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;

  // Idle pulse for spotlighted city
  const pulse =
    1 +
    (isSpotlighted ? 0.06 * Math.sin((frame - spotlightDelay) * 0.15) : 0);

  const IconComponent = ICONS[city.icon];

  return (
    <div
      style={{
        position: "absolute",
        left: `${city.x}%`,
        top: `${city.y}%`,
        transform: "translate(-50%, -50%)",
        opacity: enterOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        pointerEvents: "none",
        zIndex: isSpotlighted ? 30 : 10,
      }}
    >
      {/* Icon + glow */}
      <div
        style={{
          position: "relative",
          transform: `scale(${enterScale * pulse})`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/* Base soft glow */}
        <div
          style={{
            position: "absolute",
            width: 64,
            height: 64,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${PIN_GLOW} 0%, transparent 70%)`,
            opacity: 0.6 + 0.4 * spotlightProgress,
          }}
        />

        {/* Spotlight ring */}
        {isSpotlighted && spotlightProgress > 0 && (
          <div
            style={{
              position: "absolute",
              width: 90 + 20 * pulse,
              height: 90 + 20 * pulse,
              borderRadius: "50%",
              border: `2px solid ${SPOTLIGHT_GLOW}`,
              opacity: spotlightProgress * 0.9,
              boxShadow: `0 0 24px ${SPOTLIGHT_GLOW}`,
            }}
          />
        )}

        <IconComponent size={32} color={isSpotlighted ? SPOTLIGHT_GLOW : PIN_COLOR} />
      </div>

      {/* Main label */}
      <div
        style={{
          background: "rgba(10, 46, 28, 0.92)",
          border: `${isSpotlighted ? "1.6px" : "1.2px"} solid ${
            isSpotlighted ? SPOTLIGHT_GLOW : GOLD_ACCENT
          }`,
          borderRadius: 5,
          padding: "3px 12px",
          fontSize: 17,
          color: GOLD_TEXT,
          whiteSpace: "nowrap",
          fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
          lineHeight: 1.25,
          textAlign: "center",
          transition: "none",
          boxShadow: isSpotlighted
            ? `0 0 12px ${SPOTLIGHT_GLOW}`
            : "0 2px 6px rgba(0,0,0,0.5)",
        }}
      >
        <div>{city.name}</div>
        {city.year && (
          <div style={{ fontSize: 13, color: GOLD_ACCENT, opacity: 0.9 }}>
            {city.year}
          </div>
        )}
      </div>

      {/* Spotlight sub-label */}
      {isSpotlighted && spotlightLabel && (
        <div
          style={{
            opacity: spotlightProgress,
            transform: `translateY(${(1 - spotlightProgress) * -8}px)`,
            background: SPOTLIGHT_GLOW,
            color: "#0a2e1c",
            borderRadius: 4,
            padding: "3px 10px",
            fontSize: 15,
            fontWeight: 600,
            fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
            whiteSpace: "nowrap",
          }}
        >
          {spotlightLabel}
        </div>
      )}
    </div>
  );
};

// =============================================================================
// Main
// =============================================================================
export type IslamicMapProps = Partial<Pick<
  typeof CONFIG,
  "spotlight" | "journey" | "title" | "subtitle" | "footer" | "camera"
>>;

export const MyAnimation: React.FC<IslamicMapProps> = (props) => {
  const config = {
    ...CONFIG,
    ...props,
    camera: {
      ...CONFIG.camera,
      ...(props.camera ?? {}),
    },
  };

  const frame = useCurrentFrame();

  // Font loading
  const [handle] = useState(() => delayRender("Loading Tajawal font"));
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
        console.error("Font load failed", err);
        continueRender(handle);
      });
  }, [handle]);

  // Camera dolly
  const cameraScale = interpolate(
    frame,
    [config.camera.startFrame, config.camera.endFrame],
    [1, config.camera.scale],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const cameraRotateX = interpolate(
    frame,
    [config.camera.startFrame, config.camera.endFrame],
    [0, config.camera.rotateX],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Title fade
  const titleOpacity = interpolate(frame, [30, 60], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Look up cities for journey/spotlight
  const cityById = Object.fromEntries(MAP_CITIES.map((c) => [c.id, c]));
  const spotlightCityId = config.spotlight?.cityId ?? null;

  // Pre-compute journey path as a single SVG path string
  const journeyPoints = config.journey
    ? config.journey.path.map((id) => cityById[id]).filter(Boolean)
    : [];
  const journeyD =
    journeyPoints.length > 1
      ? journeyPoints
          .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
          .join(" ")
      : "";

  // Total length for stroke-dashoffset animation
  const journeyLength = (() => {
    if (journeyPoints.length < 2) return 0;
    let sum = 0;
    for (let i = 1; i < journeyPoints.length; i++) {
      const dx = journeyPoints[i].x - journeyPoints[i - 1].x;
      const dy = journeyPoints[i].y - journeyPoints[i - 1].y;
      sum += Math.sqrt(dx * dx + dy * dy);
    }
    return sum * 1.05; // a touch of slack
  })();

  // Journey draw progress
  const journeyProgress = config.journey
    ? interpolate(
        frame - config.journey.startFrame,
        [0, config.journey.drawDuration],
        [0, 1],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      )
    : 0;

  // Journey label fade in after the line completes
  const journeyLabelOpacity = config.journey
    ? interpolate(
        frame - (config.journey.startFrame + config.journey.drawDuration * 0.75),
        [0, 20],
        [0, 1],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      )
    : 0;

  // Journey label placed at the geometric midpoint of the path
  const journeyLabelPos = (() => {
    if (journeyPoints.length === 0) return { x: 50, y: 50 };
    // Use the middle city as the anchor
    const midIndex = Math.floor(journeyPoints.length / 2);
    const p = journeyPoints[midIndex];
    return { x: p.x, y: p.y - 6 };
  })();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a2e1c",
        overflow: "hidden",
        perspective: 2000,
        perspectiveOrigin: "center center",
      }}
    >
      {/* Camera rig */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `scale(${cameraScale}) rotateX(${cameraRotateX}deg)`,
          transformOrigin: "center center",
          transformStyle: "preserve-3d",
        }}
      >
        {/* Map image */}
        <Img
          src={staticFile("map-bg.png")}
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
              "linear-gradient(135deg, rgba(10,46,28,0.35) 0%, rgba(10,46,28,0.15) 50%, rgba(10,46,28,0.45) 100%)",
            mixBlendMode: "multiply",
            pointerEvents: "none",
          }}
        />
        {/* Vignette */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.4) 100%)",
            pointerEvents: "none",
          }}
        />

        {/* ------------------------------------------------------------- */}
        {/* JOURNEY LINE (drawn behind pins) */}
        {/* ------------------------------------------------------------- */}
        {config.journey && journeyD && (
          <svg
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              pointerEvents: "none",
              overflow: "visible",
            }}
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <defs>
              {/* Gradient along the line for a warmer tip */}
              <linearGradient id="journeyGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="rgba(232, 200, 116, 0.4)" />
                <stop offset="100%" stopColor="rgba(255, 235, 160, 1)" />
              </linearGradient>
              <filter id="journeyGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="0.8" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Ghost full path (very dim) */}
            <path
              d={journeyD}
              fill="none"
              stroke="rgba(232, 200, 116, 0.15)"
              strokeWidth="0.35"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="1.5 1.5"
            />

            {/* Animated solid path */}
            <path
              d={journeyD}
              fill="none"
              stroke={config.journey.color}
              strokeWidth="0.55"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={journeyLength}
              strokeDashoffset={journeyLength * (1 - journeyProgress)}
              filter="url(#journeyGlow)"
            />

            {/* Small dots at each waypoint */}
            {journeyPoints.map((p, i) => (
              <circle
                key={i}
                cx={p.x}
                cy={p.y}
                r="0.7"
                fill={GOLD_ACCENT}
                opacity={interpolate(journeyProgress, [0, 1], [0, 1])}
              />
            ))}
          </svg>
        )}

        {/* Journey label */}
        {config.journey?.label && (
          <div
            style={{
              position: "absolute",
              left: `${journeyLabelPos.x}%`,
              top: `${journeyLabelPos.y}%`,
              transform: "translate(-50%, -100%)",
              opacity: journeyLabelOpacity,
              background: "rgba(10, 46, 28, 0.9)",
              border: `1.4px solid ${GOLD_ACCENT}`,
              borderRadius: 5,
              padding: "4px 14px",
              fontSize: 18,
              color: GOLD_TEXT,
              fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              zIndex: 20,
              boxShadow: `0 2px 10px rgba(0,0,0,0.6)`,
            }}
          >
            {config.journey.label}
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* CITY PINS */}
        {/* ------------------------------------------------------------- */}
        {MAP_CITIES.map((city, i) => {
          const entryDelay = 20 + i * 4; // quick stagger (all in <1s)
          const isSpotlighted = city.id === spotlightCityId;
          return (
            <CityPin
              key={city.id}
              city={city}
              entryDelay={entryDelay}
              isSpotlighted={isSpotlighted}
              spotlightDelay={config.spotlight?.startFrame ?? 0}
              spotlightLabel={config.spotlight?.label}
            />
          );
        })}

        {/* Title */}
        <AbsoluteFill
          style={{
            direction: "rtl",
            fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "flex-start",
            paddingTop: 60,
            pointerEvents: "none",
            opacity: titleOpacity,
          }}
        >
          <div
            style={{
              fontSize: 38,
              color: GOLD_ACCENT,
              letterSpacing: 10,
              marginBottom: 8,
              textShadow: `0 2px 12px rgba(0,0,0,0.7)`,
            }}
          >
            {config.title}
          </div>
          <div
            style={{
              fontSize: 20,
              color: GOLD_TEXT,
              opacity: 0.85,
              letterSpacing: 4,
              textShadow: `0 2px 8px rgba(0,0,0,0.7)`,
            }}
          >
            {config.subtitle}
          </div>
        </AbsoluteFill>

        {/* Footer */}
        <AbsoluteFill
          style={{
            direction: "rtl",
            fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "flex-end",
            paddingBottom: 55,
            pointerEvents: "none",
            opacity: titleOpacity,
          }}
        >
          <div
            style={{
              position: "relative",
              width: 520,
              height: 1,
              background: `linear-gradient(to right, transparent 0%, ${GOLD_DIM} 25%, ${GOLD_DIM} 75%, transparent 100%)`,
              marginBottom: 22,
            }}
          >
            <div
              style={{
                position: "absolute",
                top: -5,
                left: "50%",
                transform: "translateX(-50%) rotate(45deg)",
                width: 10,
                height: 10,
                backgroundColor: GOLD_TEXT,
              }}
            />
          </div>
          <div
            style={{
              fontSize: 22,
              color: GOLD_TEXT,
              opacity: 0.9,
              letterSpacing: 1,
              textShadow: `0 2px 8px rgba(0,0,0,0.7)`,
            }}
          >
            {config.footer}
          </div>
        </AbsoluteFill>
      </div>
    </AbsoluteFill>
  );
};
// ─── Public type — the LLM/pipeline sees this ─────────────
// MAP_CITIES is intentionally static and is NOT a public prop.
// Python may change spotlight, journey, text, or camera only.
export type islamicMapProps = {
  spotlight?: typeof CONFIG.spotlight;
  journey?: typeof CONFIG.journey;
  title?: string;
  subtitle?: string;
  footer?: string;
  camera?: Partial<typeof CONFIG.camera>;
};

export const islamicMapDefaults = CONFIG;
export const IslamicMap = MyAnimation;
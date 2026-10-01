import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

// =============================================================================
// Types
// =============================================================================
export interface DateEvent {
  from: number;
  hijri: string;
  miladi?: string;
  label?: string;
}

export interface DateOverlayProps {
  events: DateEvent[];
  position?: "top-right" | "top-left" | "bottom-right" | "bottom-left";
  transitionFrames?: number;
  margin?: number;
}

// --- Colors (matched to the design system) ---
const GOLD_TEXT = "rgba(240, 222, 165, 0.95)";
const GOLD_ACCENT = "#e8c874";
const GOLD_DIM = "#8a6f3c";
const GOLD_SOFT = "rgba(217, 196, 122, 0.85)";
const PILL_BG = "rgba(10, 46, 28, 0.85)";

// =============================================================================
// Position helper
// =============================================================================
const getPositionStyle = (
  position: string,
  margin: number,
): React.CSSProperties => {
  switch (position) {
    case "top-left":
      return { top: margin, left: margin };
    case "bottom-right":
      return { bottom: margin, right: margin };
    case "bottom-left":
      return { bottom: margin, left: margin };
    case "top-right":
    default:
      return { top: margin, right: margin };
  }
};

// =============================================================================
// DateOverlay — pure, transparent, absolutely positioned
// =============================================================================
const DateOverlay: React.FC<DateOverlayProps> = ({
  events,
  position = "top-right",
  transitionFrames = 18,
  margin = 48,
}) => {
  const frame = useCurrentFrame();

  if (events.length === 0) return null;

  // Find current event — largest `from` <= frame
  let currentIndex = 0;
  for (let i = 0; i < events.length; i++) {
    if (events[i].from <= frame) currentIndex = i;
    else break;
  }
  const current = events[currentIndex];
  const next = events[currentIndex + 1];

  const enterProgress = interpolate(
    frame,
    [current.from, current.from + transitionFrames],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const exitProgress = next
    ? interpolate(
        frame,
        [next.from, next.from + transitionFrames],
        [0, 1],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      )
    : 0;

  const opacity = Math.min(enterProgress, 1 - exitProgress);
  const translateY =
    interpolate(enterProgress, [0, 1], [16, 0]) -
    interpolate(exitProgress, [0, 1], [0, 16]);

  const pulse = enterProgress * (1 - enterProgress) * 4;
  const glowStrength = pulse * 0.7;

  const posStyle = getPositionStyle(position, margin);

  return (
    <div
      style={{
        position: "absolute",
        ...posStyle,
        direction: "rtl",
        display: "flex",
        flexDirection: "column",
        alignItems: position.includes("right") ? "flex-end" : "flex-start",
        gap: 8,
        pointerEvents: "none",
        opacity,
        transform: `translateY(${translateY}px)`,
        zIndex: 100,
      }}
    >
      <div
        style={{
          position: "relative",
          background: PILL_BG,
          border: `1.5px solid ${GOLD_ACCENT}`,
          borderRadius: 8,
          padding: "10px 22px",
          fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
          boxShadow: `
            0 4px 12px rgba(0,0,0,0.5),
            0 0 ${16 * glowStrength}px rgba(232, 200, 116, ${glowStrength})
          `,
          display: "flex",
          alignItems: "center",
          gap: 14,
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: GOLD_TEXT,
            letterSpacing: 1,
            textShadow: `0 0 ${8 * glowStrength}px ${GOLD_ACCENT}`,
          }}
        >
          {current.hijri}
        </span>

        {current.miladi && (
          <span
            style={{
              display: "inline-block",
              width: 6,
              height: 6,
              backgroundColor: GOLD_DIM,
              transform: "rotate(45deg)",
              opacity: 0.9,
            }}
          />
        )}

        {current.miladi && (
          <span
            style={{
              fontSize: 22,
              color: GOLD_SOFT,
              letterSpacing: 1,
            }}
          >
            {current.miladi}
          </span>
        )}
      </div>

      {current.label && (
        <div
          style={{
            padding: "4px 12px",
            fontFamily: "'Tajawal', 'Noto Naskh Arabic', serif",
            fontSize: 15,
            color: GOLD_SOFT,
            letterSpacing: 4,
            opacity: 0.85,
            textAlign: position.includes("right") ? "right" : "left",
          }}
        >
          {current.label}
        </div>
      )}
    </div>
  );
};

export default DateOverlay
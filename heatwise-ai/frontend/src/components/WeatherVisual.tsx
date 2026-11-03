import type { WeatherScene } from "../lib/weatherScene";

/**
 * Decorative atmospheric illustration for the weather hero. Purely visual (aria-hidden): the scene is
 * chosen from real values by sceneFor(), and the text beside it carries the information.
 * Motion comes from CSS classes that prefers-reduced-motion turns off.
 */
export function WeatherVisual({ scene, size = 220 }: { scene: WeatherScene; size?: number }) {
  const hot = scene === "extreme-heat" || scene === "hot";
  const sunColor = scene === "extreme-heat" ? "#ff6b3d" : scene === "hot" ? "#ff9a3d" : "#ffc24a";
  const showSun = scene !== "rain" && scene !== "none";
  const rays = scene === "extreme-heat" ? 16 : 12;

  return (
    <svg
      viewBox="0 0 240 240"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className="max-w-full"
    >
      <defs>
        <radialGradient id="hw-sun-core" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fff4d6" />
          <stop offset="45%" stopColor={sunColor} />
          <stop offset="100%" stopColor={sunColor} stopOpacity="0.85" />
        </radialGradient>
        <radialGradient id="hw-sun-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={sunColor} stopOpacity="0.45" />
          <stop offset="100%" stopColor={sunColor} stopOpacity="0" />
        </radialGradient>
        <linearGradient id="hw-cloud-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#dbe6f7" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#8fa4c7" stopOpacity="0.85" />
        </linearGradient>
        <linearGradient id="hw-haze" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff8a4c" stopOpacity="0" />
          <stop offset="50%" stopColor="#ff8a4c" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#ff8a4c" stopOpacity="0" />
        </linearGradient>
      </defs>

      {showSun && (
        <g>
          <circle cx="120" cy="104" r="104" fill="url(#hw-sun-halo)" className="hw-sun-pulse" />
          <g className="hw-rays" style={{ transformBox: "fill-box" }}>
            {Array.from({ length: rays }, (_, i) => {
              const angle = (i * 360) / rays;
              return (
                <rect
                  key={i}
                  x="117"
                  y="22"
                  width="6"
                  height={hot ? 26 : 20}
                  rx="3"
                  fill={sunColor}
                  opacity={i % 2 ? 0.55 : 0.9}
                  transform={`rotate(${angle} 120 104)`}
                />
              );
            })}
          </g>
          <circle cx="120" cy="104" r="46" fill="url(#hw-sun-core)" />
        </g>
      )}

      {(scene === "warm" || scene === "mild" || scene === "rain") && (
        <g className={scene === "rain" ? "hw-cloud-slow" : "hw-cloud"}>
          <path
            d="M62 168c-17 0-30-12-30-27s13-27 30-27c4-21 22-36 44-36 20 0 37 13 42 31 3-1 7-1 10-1 18 0 32 13 32 30s-14 30-32 30z"
            fill="url(#hw-cloud-fill)"
            opacity={scene === "rain" ? 0.95 : 0.8}
          />
        </g>
      )}

      {scene === "rain" && (
        <g className="hw-rain" stroke="#7cc8ff" strokeWidth="3" strokeLinecap="round">
          {[70, 96, 122, 148, 174].map((x, i) => (
            <line key={x} x1={x} y1="182" x2={x - 6} y2="200" style={{ animationDelay: `${i * 0.18}s` }} />
          ))}
        </g>
      )}

      {hot && (
        <g>
          {[176, 192, 208].map((y, i) => (
            <rect
              key={y}
              x="40"
              y={y}
              width="160"
              height="7"
              rx="3.5"
              fill="url(#hw-haze)"
              className="hw-shimmer"
              style={{ animationDelay: `${i * 0.9}s`, transformBox: "fill-box", transformOrigin: "center" }}
            />
          ))}
        </g>
      )}

      {scene === "none" && (
        <g opacity="0.6">
          <circle cx="120" cy="110" r="50" fill="none" stroke="#34486c" strokeWidth="3" strokeDasharray="6 8" />
          <rect x="60" y="176" width="120" height="6" rx="3" fill="#1f2e4a" />
        </g>
      )}
    </svg>
  );
}

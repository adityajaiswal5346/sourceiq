/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand — indigo/violet (Anthropic-adjacent, professional)
        brand: {
          DEFAULT: "#6366f1",   // indigo-500
          hover:   "#4f46e5",   // indigo-600
          muted:   "#eef2ff",   // indigo-50
          border:  "#c7d2fe",   // indigo-200
          text:    "#4338ca",   // indigo-700
        },
        // Surfaces — near-white chrome
        surface: {
          DEFAULT: "#ffffff",
          subtle:  "#fafafa",
          muted:   "#f4f4f5",   // zinc-100
          raised:  "#f8f8f8",
        },
        // Borders — ultra-subtle
        edge: {
          DEFAULT: "#e4e4e7",   // zinc-200
          strong:  "#d1d5db",   // gray-300
          subtle:  "#f1f1f1",
        },
        // Text — zinc scale
        ink: {
          DEFAULT: "#18181b",   // zinc-900
          secondary:"#52525b",  // zinc-600
          tertiary: "#a1a1aa",  // zinc-400
          disabled: "#d4d4d8",  // zinc-300
        },
        // Semantic
        success: {
          DEFAULT: "#22c55e",   // green-500
          bg:      "#f0fdf4",
          border:  "#bbf7d0",
          text:    "#15803d",
        },
        warning: {
          DEFAULT: "#f59e0b",
          bg:      "#fffbeb",
          border:  "#fde68a",
          text:    "#b45309",
        },
        danger: {
          DEFAULT: "#ef4444",
          bg:      "#fef2f2",
          border:  "#fecaca",
          text:    "#b91c1c",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "16px", letterSpacing: "0.025em" }],
        xs:    ["11px", { lineHeight: "16px" }],
        sm:    ["12px", { lineHeight: "18px" }],
        base:  ["13px", { lineHeight: "20px" }],
        md:    ["14px", { lineHeight: "22px" }],
        lg:    ["15px", { lineHeight: "24px" }],
        xl:    ["16px", { lineHeight: "26px" }],
        "2xl": ["20px", { lineHeight: "28px", letterSpacing: "-0.25px" }],
        "3xl": ["24px", { lineHeight: "32px", letterSpacing: "-0.5px" }],
        "4xl": ["30px", { lineHeight: "38px", letterSpacing: "-0.75px" }],
        "5xl": ["36px", { lineHeight: "44px", letterSpacing: "-1px"    }],
      },
      borderRadius: {
        sm:   "5px",
        md:   "7px",
        lg:   "9px",
        xl:   "12px",
        "2xl":"16px",
        "3xl":"20px",
      },
      boxShadow: {
        xs:    "0 1px 2px rgba(0,0,0,0.05)",
        sm:    "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        md:    "0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -1px rgba(0,0,0,0.04)",
        lg:    "0 10px 15px -3px rgba(0,0,0,0.07), 0 4px 6px -2px rgba(0,0,0,0.04)",
        focus: "0 0 0 3px rgba(99,102,241,0.15)",
        card:  "0 1px 3px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.04)",
      },
      animation: {
        "fade-in":   "fadeIn 0.15s ease-out",
        "slide-up":  "slideUp 0.18s cubic-bezier(0.16,1,0.3,1)",
        "spin-fast": "spin 0.65s linear infinite",
        "pulse-dim": "pulse 2s cubic-bezier(0.4,0,0.6,1) infinite",
      },
      keyframes: {
        fadeIn:  { from:{opacity:"0"}, to:{opacity:"1"} },
        slideUp: { from:{opacity:"0",transform:"translateY(6px)"}, to:{opacity:"1",transform:"translateY(0)"} },
      },
    },
  },
  plugins: [],
};

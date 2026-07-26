import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Core background colors
        surface: "#F8FAFC", // gray-50
        ink: "#0F172A", // gray-900
        
        // Brand blue
        accent: {
          DEFAULT: "#2563EB", // blue-600
          hover: "#1D4ED8", // blue-700
          active: "#1E40AF", // blue-800
          light: "#DBEAFE", // blue-100
          faint: "#EFF6FF", // blue-50
        },

        // Semantic states
        success: {
          DEFAULT: "#10B981", // emerald-500
          light: "#ECFDF5", // emerald-50
          dark: "#059669", // emerald-600
        },
        warning: {
          DEFAULT: "#F59E0B", // amber-500
          light: "#FFFBEB", // amber-50
          dark: "#D97706", // amber-600
        },
        danger: {
          DEFAULT: "#EF4444", // red-500
          light: "#FEF2F2", // red-50
          dark: "#DC2626", // red-600
        }
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "monospace"],
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        'card-hover': '0 4px 12px rgba(0,0,0,0.08)',
        'elevated': '0 10px 25px rgba(0,0,0,0.1)',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        }
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      }
    },
  },
  plugins: [],
};

export default config;

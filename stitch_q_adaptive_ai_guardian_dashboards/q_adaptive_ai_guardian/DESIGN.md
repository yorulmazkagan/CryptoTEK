---
name: Q-Adaptive AI Guardian
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#3d494c'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#6d797d'
  outline-variant: '#bcc9cd'
  surface-tint: '#00687a'
  primary: '#00687a'
  on-primary: '#ffffff'
  primary-container: '#06b6d4'
  on-primary-container: '#00424f'
  inverse-primary: '#4cd7f6'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#bc0b3b'
  on-tertiary: '#ffffff'
  tertiary-container: '#ff7f8b'
  on-tertiary-container: '#7d0023'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#acedff'
  primary-fixed-dim: '#4cd7f6'
  on-primary-fixed: '#001f26'
  on-primary-fixed-variant: '#004e5c'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdadb'
  tertiary-fixed-dim: '#ffb2b7'
  on-tertiary-fixed: '#40000d'
  on-tertiary-fixed-variant: '#92002a'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.05em
  mono-data:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  grid-margin: 2rem
  gutter: 1.5rem
  stack-sm: 0.5rem
  stack-md: 1rem
  stack-lg: 2rem
  section-padding: 4rem
---

## Brand & Style
The design system for this product is engineered to project high-fidelity security, real-time intelligence, and Web3 sophistication. The brand personality is vigilant, technical, and hyper-modern, functioning as a "Digital Sentinel" for cyber-security assets.

The visual style merges **Glassmorphism** with **Technical Minimalism**. It utilizes a strictly light-themed environment to differentiate from the typical "dark mode" trope of security tools, favoring a laboratory-clean aesthetic. High-frequency information is contained within frosted glass modules, while critical states are communicated through "Neon Pulse" borders and shadows. The interface should feel like an advanced diagnostic heads-up display (HUD) rendered on a physical glass substrate.

## Colors
The palette is rooted in a "Clinical White" foundation using `bg-slate-50`. 

- **Primary (Neon Cyan):** Used for active data streams, AI processing indicators, and primary actions.
- **Secondary (Neon Emerald):** Reserved exclusively for "Safe" status, successful cryptographic validations, and healthy network nodes.
- **Tertiary (Neon Rose):** Utilized for "Panic" states, high-priority vulnerabilities, and unauthorized access attempts.
- **Neutral (Slate):** Handles structural elements, secondary text, and inactive states to ensure the neon accents remain the focal point.

In "Panic State," the UI should transition key accent borders and glows from Cyan/Emerald to Rose/Crimson to trigger immediate cognitive urgency.

## Typography
The system employs a dual-sans-serif approach. **Geist** is used for headlines, labels, and data points to provide a technical, "monospaced-adjacent" feel that suggests precision. **Inter** is used for body copy to maintain high readability during long-form security report analysis.

- Use **Label-MD** (uppercase) for category headers and table columns.
- Use **Mono-Data** for wallet addresses, transaction hashes, and log entries.
- Maintain tight tracking on display type to reinforce the "engineered" look.

## Layout & Spacing
The layout follows a strict **12-column fluid grid** for desktop, collapsing to a single-column layout for mobile. 

- **Grid Philosophy:** High-density information. Cards should be aligned to a 4-column or 6-column span to maintain a modular "dashboard" feel.
- **Safe Areas:** Use a 32px (2rem) outer margin on all viewports to ensure the neon glows are not clipped by the screen edge.
- **Vertical Rhythm:** Elements are stacked using a base-8 spacing system (8px, 16px, 24px, 32px) to ensure mathematical alignment.

## Elevation & Depth
Depth is achieved through **Glassmorphism** and **Luminous Accents** rather than traditional drop shadows.

- **Surface Layers:** All cards use a background of `rgba(255, 255, 255, 0.7)` with a `backdrop-filter: blur(12px)`. 
- **The Neon Glow:** Instead of standard shadows, use Tailwind arbitrary values for colored glows:
    - *Safe Glow:* `shadow-[0_0_15px_rgba(6,182,212,0.12)]`
    - *Panic Glow:* `shadow-[0_0_20px_rgba(244,63,94,0.2)]`
- **Borders:** Surfaces feature a 1px solid border. In active or "Safe" states, use a semi-transparent Cyan border; in "Panic" states, use a semi-transparent Rose border.

## Shapes
This design system uses **Soft** geometry (4px - 12px) to maintain a professional, architectural feel. 

- **Containers:** Standard cards use `rounded-md` (0.25rem). 
- **Buttons & Inputs:** Use `rounded-md` to maintain consistency with the grid.
- **Status Pills:** Use `rounded-full` for status indicators to distinguish them from interactive buttons.
- **Avoid:** Do not use sharp 0px corners, as they appear too aggressive, nor circular "pill" shapes for main UI modules, as they feel too "consumer-grade."

## Components

### Glass Cards
The core container. Must include `backdrop-blur-md`, `bg-white/70`, and a `border-slate-200/50`. For critical alerts, the border switches to `border-rose-500/50` with a matching neon shadow.

### Status-Driven Buttons
- **Primary (Safe):** Background white, 1px border of Neon Cyan, text Cyan, and a `shadow-[0_0_10px_rgba(6,182,212,0.3)]` on hover.
- **Primary (Panic):** Background Neon Rose, text white, aggressive `shadow-[0_0_20px_rgba(244,63,94,0.4)]`.

### Data Grids
Tables should be borderless but utilize alternating "Glass" row highlights on hover. Column headers must use the `Label-MD` typography token in `text-slate-500`.

### Neon Accents
Use 2px height horizontal lines (`bg-gradient-to-r from-cyan-500 to-transparent`) as section dividers to reinforce the technical HUD aesthetic.

### Input Fields
Fields should be `bg-slate-100/50` with a bottom-only border of `slate-300`. Upon focus, the bottom border glows in `cyan-400`.
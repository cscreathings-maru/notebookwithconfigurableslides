# Changelog — NoteAI Rebranding & Configurable Slides Revamp

All notable changes to this project will be documented in this file.

---

## [v2.0.0] - 2026-07-26: NoteAI UI/UX Revamp & Rich Template Configuration

### 🎯 Overview
This major release transforms the application from **Maru / Presentation Notebook LLM** into **NoteAI**. The release introduces a complete UI/UX overhaul designed to replace basic, AI-generated placeholder layouts with a premium, human-crafted web application experience. Additionally, it integrates a comprehensive **Rich Template Configurator** that allows administrators to define custom brand tokens, upload base `.pptx` decks, and generate stakeholder-tailored presentations using the Presenton engine.

---

### ✨ New Features

#### 1. Rich Template Configuration Wizard (`/templates`)
- **4-Section Configuration**: Introduced a structured configurator covering *General Settings*, *Brand & Aesthetics*, *Layout & Formatting*, and *Base Template Upload*.
- **Live Brand Tokens**: Added visual RGB/Hex color pickers for Primary (`#2563EB`), Secondary (`#1E40AF`), and Accent (`#F59E0B`) colors, along with typography dropdowns (Inter, JetBrains Mono, Roboto, Outfit).
- **Custom PPTX Ingestion**: Enabled drag-and-drop / file browser uploads for `.pptx` base decks. The backend securely maps uploaded files and brand token JSONs into namespaced Presenton engine references.
- **Template Table Preview**: Rebuilt the templates table to display target audiences, versioning, and inline color swatch previews.

#### 2. Profiles Manager & Section Structure Builder (`/profiles`)
- **Grid-Based Profile Editor**: Redesigned `/profiles` into a clean card-based grid layout for managing presentation tones, verbosity, and slide count bounds.
- **Interactive Section Structure Builder**: Built `SectionStructureBuilder.tsx` allowing authors to dynamically add, reorder (up/down arrows), and delete outline sections and talking points.
- **Approved Template Enforcement**: Added validation ensuring stakeholder profiles are explicitly linked to approved brand templates.

#### 3. Studio & Workspace Panel Enhancement (`/projects/[id]`)
- **3-Pane Workspace Polish**: Updated the project workspace container with breadcrumb headers, responsive grid layouts, and visual hierarchy across Sources, Guide, Chat, and Studio panels.
- **Chat Styling**: Differentiated chat bubbles with Blue-600 (`bg-accent text-white`) for user messages and clean white/gray cards for AI responses.
- **Live Studio Generation**: Wired template selection dropdowns directly into the presentation generation trigger. Added animated status badges (`generating`, `ready`, `failed`) and instant `.pptx` / `.pdf` browser download buttons.

#### 4. Usage Dashboard & Quota Monitoring (`/usage`)
- **Stat Cards with Icons**: Implemented 4 prominent summary cards tracking Generations, Tokens In, Tokens Out, and Estimated Cost.
- **Animated Quota Indicator**: Created `QuotaIndicator.tsx` featuring a smooth 1000ms progress bar transition displaying monthly usage against organization limits.
- **Clean Tables**: Refactored Usage by User and Audit Log tables with hover states and aligned typography.

---

### 🎨 Branding & Visual Identity Updates

- **Global String Replacement**: Replaced all occurrences of "Maru" and "Presentation Notebook LLM" with **NoteAI** across browser titles, meta descriptions, login screens, navigation sidebars, and i18n translation bundles.
- **Curated Color Palette**: Transitioned to a clean white background with a modern **Blue-600 (`#2563EB`)** primary brand palette.
- **Typography System**: Integrated **Inter** (sans-serif) and **JetBrains Mono** (monospace) font variables into `tailwind.config.ts` and `globals.css`.
- **UI Component Hierarchy**: Standardized CSS utility tokens (`card`, `shadow-elevated`, `btn-primary`, `btn-secondary`, `input-field`) across all views.

---

### 🧪 Quality Assurance & Automated Testing

- **Automated Verification Suite**: Built `automation/verify_noteai_revamp.py` which programmatically validates:
  - Frontend static analysis and UI design token adherence.
  - Component wiring and payload mapping for templates and profiles.
  - Backend API contract execution via Python `pytest`.
- **Test Reports & Documentation**: Added `TEST_CASES.md` and `NOTEAI_TEST_REPORT.md` providing 100% verification coverage across 26 distinct test criteria.
- **Production Build Verification**: Confirmed zero TypeScript errors and successful Next.js production builds (`npm run build`).

---
*See repository commit history for granular file diffs.*

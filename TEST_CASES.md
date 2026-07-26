# NoteAI UI/UX & Feature Test Cases

This document outlines detailed test cases to verify the recent rebranding to **NoteAI**, the UI/UX revamp, and the new **Rich Template Configuration** feature.

## 1. Branding & Visual Identity Validation
**Objective:** Ensure all references to "Maru" and "Presentation Notebook LLM" have been replaced and the new visual identity is applied globally.

| Test ID | Area | Action | Expected Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **BR-01** | Global | Navigate through all pages (Login, Projects, Templates, Profiles, Usage). | The primary brand color is Blue-600 (`#2563EB`). Typography is Inter/JetBrains Mono. | |
| **BR-02** | Global | Check browser tab titles and meta descriptions. | Title reads "NoteAI". Description mentions "NoteAI". | |
| **BR-03** | Sidebar | Observe the left navigation sidebar. | The sidebar has a dark theme. The logo/brand text reads "NoteAI". Active states are clearly visible. | |
| **BR-04** | Login | Navigate to `/login` (logged out). | Page shows a centered, premium card layout. Text reads "Welcome to NoteAI". | |

---

## 2. Rich Template Configuration (New Feature)
**Objective:** Verify that administrators can create complex templates with brand tokens and that the payload is saved correctly.

| Test ID | Area | Action | Expected Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **TPL-01** | Templates | As an Admin, navigate to `/templates` and click **New Template**. | The Rich Template Configurator panel slides into view with 4 distinct sections. | |
| **TPL-02** | Templates | Fill out General Settings: Name = "Q3 Marketing", Audience = "Client Facing". | Inputs accept the data without errors. | |
| **TPL-03** | Templates | Fill out Brand & Aesthetics: Change Primary color to Red, Secondary to Gray, Font to "Roboto". | Color pickers update the hex values. Font dropdown selects "Roboto". | |
| **TPL-04** | Templates | Upload a PPTX file in the Base Template Upload section. | The drag-and-drop area updates to show the selected filename. | |
| **TPL-05** | Templates | Click **Create Template**. | The button shows a loading spinner. Upon success, the template appears in the table below. | |
| **TPL-06** | Templates | Inspect the created template in the table. | The table displays the correct Audience, Name, Version, and a visual preview of the Primary Color and Font in the "Brand Tokens" column. | |

---

## 3. Profiles Manager UI
**Objective:** Verify the new card-based Profile Editor works as expected.

| Test ID | Area | Action | Expected Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **PRF-01** | Profiles | Navigate to `/profiles` and click **New Profile**. | The Profile Editor opens with a clean, grid-based layout. | |
| **PRF-02** | Profiles | Try saving a profile without selecting a Template. | The "Create Profile" button should be disabled, or the form should prompt for the required field. | |
| **PRF-03** | Profiles | Add a new section in the **Section Structure** builder. | A new input field appears. You can reorder it using the ↑/↓ arrows and remove it using the ✕ button. | |
| **PRF-04** | Profiles | Click **Edit** on an existing Profile. | The editor populates with the existing data. The header reads "Edit [Profile Name]". | |

---

## 4. Project Workspace & Studio Panel
**Objective:** Verify the core presentation generation workflow and panel aesthetics.

| Test ID | Area | Action | Expected Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **WRK-01** | Projects | Navigate to `/projects` and click a project card. | The workspace loads with the 3-pane layout. The header shows the Project Name and breadcrumbs. | |
| **WRK-02** | Sources | In the Sources Panel, click **Add Source**. | A clean input field appears for URL/File upload. Uploading shows a loading state. | |
| **WRK-03** | Guide | Observe the Guide Panel. | It features a decorative background accent, shadow card, and clearly formatted summary text. | |
| **WRK-04** | Chat | Send a message in the Chat Panel. | User bubbles are styled blue (`bg-accent text-white`), AI bubbles are styled white/gray. Typing indicators are visible while waiting. | |
| **WRK-05** | Studio | In the Studio Panel, open the **Template** dropdown. | The template created in TPL-05 ("Q3 Marketing") is available for selection. | |
| **WRK-06** | Studio | Fill out the Studio form and click **Generate Presentation**. | The generation starts. A new item appears in the "Decks" list with a yellow "generating" status badge. | |
| **WRK-07** | Studio | Wait for the generation to complete. | The status badge turns green ("ready"). Download buttons (PPTX / PDF) appear next to the item. | |
| **WRK-08** | Studio | Click the **PPTX** download button. | The browser downloads the generated presentation file. | |

---

## 5. Usage Dashboard
**Objective:** Verify the visual upgrades to the usage tracking dashboard.

| Test ID | Area | Action | Expected Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **USG-01** | Usage | Navigate to `/usage`. | The page displays 4 prominent Stat Cards (Generations, Tokens In/Out, Cost) with icons. | |
| **USG-02** | Usage | Observe the Quota Indicator. | The progress bar shows a smooth fill percentage based on usage. Text clearly indicates usage vs limit. | |
| **USG-03** | Usage | View the "Usage by User" and "Audit Log" tables. | Tables are cleanly styled with subtle borders, alternating row hovers, and aligned text. | |

---

## Testing Notes
- **Browser Compatibility:** Test primarily on Chrome, Safari, and Firefox.
- **Responsiveness:** Ensure you resize the browser window during testing. The Sidebar should collapse, and the grid layouts (Projects, Usage stats) should stack gracefully on smaller screens.
- **Role Permissions:** Tests in sections 2, 3, and 5 require an `admin` role. If tested with a `viewer` or `author` role, the UI should gracefully show a "Permission Denied" placeholder.

# Technical Assessment: Deck Generation Workflow Revamp

## Objective

Redesign the deck generation workflow to create a seamless experience from notebook creation to presentation editing.

The new workflow should allow users to:

* Select a presentation template before generation.
* Monitor deck generation progress.
* Open the generated presentation directly in Presenton Studio.
* Download the generated presentation as a PPTX file.

---

# Current Assessment

## Existing Workflow

Current workflow:

```
Project Chat
    │
    ▼
Notebook
    │
    ▼
Deck Generation
    │
    ▼
PPTX Output
```

### Current Limitations

### 1. No Template Selection

Deck generation uses a predefined template.

Users cannot:

* Browse available templates.
* Select a preferred design.
* Preview template styles before generation.

---

### 2. Disconnected Editing Experience

Although the project already includes **Presenton Studio**, it is not integrated into the deck generation workflow.

After generation:

* Users receive the generated output.
* They cannot immediately continue editing.
* The editor exists as a separate experience.

This creates unnecessary friction between generation and editing.

---

### 3. Missing Generation Feedback

Deck generation behaves like a black box.

Users do not know:

* Whether generation has started.
* Which stage is currently running.
* Whether generation is stuck.
* Estimated completion.

---

### 4. Poor End-to-End Workflow

Current experience:

```
Notebook
    │
Generate Deck
    │
Download
```

Desired experience:

```
Notebook
    │
Select Template
    │
Generate Deck
    │
Track Progress
    │
Open in Presenton Studio
    │
Edit
    │
Export PPTX
```

---

# Proposed Architecture

## Step 1 — Template Picker

Replace the current **Deck Generation Studio** in the right project panel with a **Template Picker**.

Responsibilities:

* Display available templates.
* Show template thumbnails.
* Show template metadata.
* Allow template selection.
* Store selected template ID.

Example:

```
Project Panel

------------------------
Presentation Templates

[ Modern ]

[ Corporate ]

[ Minimal ]

[ Academic ]

------------------------

Selected:
Modern

[Generate Deck]
```

---

## Step 2 — Deck Generation

When the user clicks **Generate Deck**:

Input:

* Notebook content
* Deck outline
* Selected template
* Project metadata

Output:

* Presentation document
* Generation job

Generation should become an asynchronous job.

Example:

```
POST /decks/generate

{
    notebookId,
    templateId,
    outlineId
}
```

Return:

```
jobId
```

---

## Step 3 — Generation Status

The UI should switch from the Template Picker to a Generation Status panel.

Example:

```
Generating Presentation...

✓ Preparing notebook

✓ Building outline

⏳ Generating slides

Waiting...

```

Suggested stages:

1. Preparing notebook
2. Parsing discussions
3. Creating slide structure
4. Generating slide content
5. Applying template
6. Rendering presentation
7. Finalizing
8. Completed

Possible implementation:

* Polling API
* WebSocket
* Server-Sent Events (SSE)

---

## Step 4 — Generation Complete

When generation finishes, present two primary actions:

```
Presentation Generated

[ Open in Presenton Studio ]

[ Download PPTX ]
```

This avoids forcing users into the editor while still making it the recommended next step.

---

# Presenton Studio Integration

Selecting **Open in Presenton Studio** should navigate directly to the editor with the generated presentation already loaded.

Example:

```
/studio/:presentationId
```

The editor should load:

* Slides
* Theme
* Assets
* Speaker notes (if available)
* Presentation metadata

Users can then:

* Edit slides
* Rearrange slides
* Replace assets
* Change layouts
* Update text
* Export

---

# Export Workflow

Export should be available in two places:

## Option 1

Immediately after generation.

```
Presentation Generated

Open Studio

Download PPTX
```

## Option 2

Inside Presenton Studio.

```
File

Export

Download PPTX
```

---

# Recommended User Flow

```
Project Chat
        │
        ▼
Notebook
        │
        ▼
Upload Sources
        │
        ▼
Create Discussions
        │
        ▼
Generate Deck Outline
        │
        ▼
Open Template Picker
        │
        ▼
Select Template
        │
        ▼
Generate Deck
        │
        ▼
View Generation Progress
        │
        ▼
Generation Complete
      ┌───────────────┐
      │               │
      ▼               ▼
Open Studio     Download PPTX
      │
      ▼
Edit Presentation
      │
      ▼
Export PPTX
```

---

# UI Changes

## Current Right Panel

```
Notebook

------------------------

Deck Generation

Generate

------------------------
```

## Proposed Right Panel

Before generation:

```
Presentation Templates

Modern

Corporate

Minimal

Academic

Generate
```

During generation:

```
Generating Presentation...

Preparing...

Generating Slides...

Applying Theme...

```

After completion:

```
Presentation Ready

Open in Presenton Studio

Download PPTX
```

---

# Technical Considerations

## Backend

* Support asynchronous deck generation jobs.
* Persist generation status.
* Associate generated presentations with projects.
* Store the selected template identifier with each generation request.
* Expose endpoints for job status, presentation retrieval, and downloads.

## Frontend

* Replace the existing Deck Generation panel with a Template Picker.
* Display real-time generation progress.
* Handle job polling or live updates.
* Provide clear success and failure states.
* Enable navigation to Presenton Studio using the generated presentation ID.

## Presenton Integration

Presenton Studio should become the default post-generation editing environment rather than a standalone tool. Deck generation is responsible for producing an editable presentation, while Presenton Studio is responsible for refinement and export.

---

# Success Criteria

The revamp is considered successful when:

* Users can select a template before generating a deck.
* Generation progress is visible throughout the process.
* Completed presentations can be opened directly in Presenton Studio.
* Users can edit the generated presentation immediately.
* Users can download the presentation as a PPTX either directly after generation or from within the editor.
* The overall workflow feels continuous, eliminating unnecessary transitions between deck generation and editing.

This assessment is structured like a lightweight engineering design document, making it suitable for implementation planning, architectural discussions, or handing off to another AI model for code generation. It clearly separates the product goals, system architecture, UI changes, backend responsibilities, and success criteria.

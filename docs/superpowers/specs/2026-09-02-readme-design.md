# DashPi README Design

**Date:** 2026-09-02  
**Status:** Approved for implementation planning  
**Audience:** Capstone evaluators, portfolio visitors, and developers

## 1. Objective

Create a Korean-first repository landing page that explains DashPi's value within seconds, demonstrates the implemented prototype honestly, and lets a developer reproduce and verify the current software without reading the entire repository.

The README will present DashPi as an offline-first smart dashcam capstone project: accident footage is preserved before analysis, a local vision model produces an advisory report, and results leave the device through an on-demand local Wi-Fi path or a network-free animated QR path.

## 2. Content Strategy

Use a balanced capstone-and-developer narrative:

1. Establish the problem, stakeholder, and value proposition.
2. Show the working browser interfaces as evidence.
3. Explain the architecture and incident flow visually.
4. Distinguish implemented software from hardware acceptance work.
5. Provide reproducible setup, run, and test instructions.
6. Link detailed requirements and technical decisions instead of duplicating them.

Korean will be the primary language. Established technical names, commands, API paths, and state identifiers will remain in English for accuracy.

## 3. README Structure

The README will contain these sections in order:

1. Hero: existing DashPi mark, capstone label, concise value statement, and truthful technology badges
2. Project summary: problem, target user, and solution
3. Key differentiators: offline operation, evidence-first failure handling, dual transfer, integrity verification
4. Prototype gallery: real captures of the incident viewer, optical sender, and optical receiver
5. System architecture: a GitHub-native Mermaid flowchart
6. Incident lifecycle: a compact Mermaid state or sequence diagram including failure paths
7. Transfer comparison: local Wi-Fi versus animated QR, with intended payload and trade-offs
8. Implementation status: completed software capabilities separated from Raspberry Pi hardware acceptance work
9. Quick start: prerequisites, installation, incident simulation, local server, and browser entry points
10. Verification: Python and TypeScript test commands plus evidence-backed acceptance scenarios
11. Data integrity, security, privacy, and AI limitations
12. Storage and repository structure
13. API summary
14. Project documents and external references

GitHub's generated document outline will replace a manually maintained table of contents.

## 4. Visual System

Visuals will use repository-native and implementation-derived material:

- Reuse `src/dashpi/web/icon.svg` as the project mark.
- Capture the three real web interfaces from the current application and store optimized images under `docs/assets/`.
- Use Mermaid source in the README for architecture and lifecycle diagrams so diagrams remain editable, searchable, and natively rendered by GitHub.
- Use compact Markdown tables for transfer and implementation-status comparisons.

AI-generated concept imagery will not be used. It could imply finished hardware that the repository does not yet implement. The actual prototype screens provide stronger capstone evidence.

Every screenshot will have descriptive alternative text. Diagrams will use short labels and avoid color-dependent meaning.

## 5. Accuracy Boundaries

The README will describe only capabilities present in code or explicitly label them as later hardware acceptance work.

Implemented software includes desktop video segmentation and clip creation, local Ollama analysis, atomic artifact storage, SHA-256 verification, ranged HTTP video delivery, animated optical frames, browser reconstruction, and offline receiver behavior.

Raspberry Pi camera capture, physical trigger wiring, display integration, hotspot lifecycle control, thermal and power validation, and physical camera-to-display throughput will be listed as pending hardware acceptance. Automatic crash detection, cloud services, native mobile applications, confidential optical transfer, and legal fault determination remain outside the MVP.

No license, institution, course number, team identity, or benchmark result will be invented. These details will be omitted unless already supported by repository evidence.

## 6. Reproducibility and Verification

Quick-start commands will be tested against the current project before publication. The README will identify Python, FFmpeg/ffprobe, Ollama, and Node.js requirements only where each is actually needed.

Verification claims will be tied to runnable tests. Test counts or pass claims will be included only if obtained from a fresh run during README implementation. Broken or incomplete setup metadata discovered during verification will be reported rather than hidden.

Screenshot generation will use deterministic local fixture data and the real FastAPI-served web pages. Temporary fixture data will not be committed.

## 7. Failure and Safety Communication

The README will make these design rules visible:

- A valid accident clip remains available when AI analysis fails.
- Partial or hash-mismatched artifacts are never presented as complete.
- Optical transfer is line-of-sight and not encrypted.
- AI output is advisory and must not be presented as a legal determination of fault.
- The server is designed for a device-local network, not public internet exposure.

## 8. Reference Basis

- GitHub, “About the repository README file”: explain what the project does, why it is useful, how to start, and where to find help; use relative repository links for portability.
- GitHub, “Creating diagrams”: use fenced Mermaid blocks for diagrams rendered directly in Markdown.
- GitHub Open Source Guides, “Starting an Open Source Project”: make the project's purpose and expected use legible to visitors.
- Australian National University School of Engineering, “Assessment Guide — Capstone Project”: communicate the problem, stakeholders, value, solution rationale, outcomes, and prototype evidence to a multidisciplinary audience with visual coherence.

## 9. Acceptance Criteria

- A new visitor can identify the problem, user, and core value from the opening viewport.
- The README includes three genuine prototype screenshots and at least two purposeful Mermaid diagrams.
- Implemented and pending capabilities are visibly separated.
- Setup, server, simulation, and test commands are runnable or clearly scoped to their prerequisites.
- All local links and image paths resolve from the repository root.
- Visuals have alternative text and the README remains understandable without rendered images.
- Detailed material links to PRD and TRD rather than duplicating them.
- The final README contains no placeholders, unsupported claims, or fabricated project metadata.

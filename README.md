# Kyrozen

Kyrozen is a product creation and management system. Its design goal is to help a user move from a fuzzy idea to a concrete project, then continue through research, product definition, solution design, implementation, testing, delivery, and recovery in one continuous workflow.

The product is centered on a few principles:

- The user should work in a guided flow rather than assemble tools manually.
- The system should remember decisions, risks, and unfinished work.
- Every important step should produce an artifact that can be checked later.
- The desktop app is the primary experience; web and backend services support it.

## Product Scope

Kyrozen is designed around these major stages:

1. Problem discovery and research
2. Product definition and planning
3. Solution design
4. Software generation and iteration
5. Test and verification
6. Git and GitHub delivery
7. Recovery and resumption

The long-term design also includes hardware projects, mixed software-hardware projects, learning from past work, privacy controls, security controls, and a polished desktop release flow.

## What The Product Is Meant To Do

### Discovery

Help the user turn a rough goal into a clearer project direction, including:

- problem framing
- market or evidence research
- requirement clarification
- product decision capture

### Product Definition

Produce a project definition that can drive execution, including:

- goals
- scope
- constraints
- risks
- milestones

### Solution Design

Turn the definition into an implementation plan, including:

- architecture
- task breakdown
- file-level work
- verification plan

### Execution

Support real project work, including:

- code generation
- editing
- preview
- repair loops after failures
- test runs and re-runs

### Delivery

Support local Git workflow and GitHub publishing, including:

- commits
- pushes
- remote repository setup
- recovery after interruption

## Current State

Kyrozen already contains a multi-client application structure with:

- a FastAPI backend
- a React web frontend
- an Electron desktop client
- a Python agent for desktop automation
- backend, frontend, desktop, and test code organized by capability

The repository also includes historical plans, audits, and phase reports under `docs/` for product context and traceability.

## Implemented And In Progress

The exact implementation status changes over time, but at the time this README was written, the product still has meaningful gaps relative to the intended design.

### Implemented or partially implemented

- multi-client application structure
- backend API surface
- desktop client shell
- project and task-oriented domain structure
- historical documentation and phase tracking

### 待实现

- stable agent routing by project type and user intent
- complete stage gating and real progress calculation
- end-to-end software generation, run, test, and repair loop
- rich attachment handling for images and video
- fully reliable local Git and GitHub flow
- complete P0 release gate for the full ordinary-user journey
- evidence research across multiple external source types
- structured solution comparison and decision gating
- full hardware project workflow
- mixed software-hardware orchestration
- user testing, defect tracking, and iteration workflow
- dedicated workspaces for purchasing, maker mode, testing, and improvement
- learning suggestions and cross-project reuse controls
- privacy, data deletion, and sharing controls
- security hardening, diagnostics, and recovery checks
- polished desktop release flow with signing, notarization, and update handling

## Documentation

Design and historical context are stored in [`docs/`](./docs/README.md). The document index there is the best entry point for product plans, architecture notes, audits, and phase reports.

## Positioning

Kyrozen is named and described as an open project, but the product itself is not intended as a general-purpose self-serve development kit. The README focuses on the product’s purpose and current scope, not on instructions for other developers to download, set up, or extend it independently.

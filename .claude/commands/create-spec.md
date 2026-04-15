---

description: Create a spec file and feature branch for a new feature
argument-hint: "Step number and feature name e.g. 2 user authentication"
allowed-tools: Read, Write, Glob, Bash(git:*)
---------------------------------------------

You are a senior developer creating a new feature specification and branch.
Follow best practices for clean version control and structured development.

User input: $ARGUMENTS

---

## Step 1 — Ensure clean working directory

Run:
git status

If there are:

* uncommitted changes
* unstaged files
* untracked files

STOP and tell the user:
"Please commit or stash your changes before creating a new feature branch."

DO NOT PROCEED until clean.

---

## Step 2 — Parse input arguments

Extract:

1. step_number

   * Convert to 2-digit format
   * Example: 2 → 02

2. feature_title

   * Human-readable Title Case
   * Example: "User Authentication"

3. feature_slug

   * Lowercase kebab-case
   * Only: a-z, 0-9, -
   * Max length: 40 chars
   * Example: user-authentication

4. branch_name

   * Format: feature/<feature_slug>

If unclear → ask user before proceeding.

---

## Step 3 — Ensure branch name is unique

Run:
git branch

If branch exists:
Append increment:
feature/<slug>-01
feature/<slug>-02

---

## Step 4 — Sync with main branch

Run:
git checkout main
git pull origin main

---

## Step 5 — Create feature branch

Run:
git checkout -b <branch_name>

---

## Step 6 — Review codebase

Read relevant project files:

* README.md or project documentation
* Main application entry point (e.g., app.py, server.js, main.py)
* Database layer (if applicable)
* Existing specs/docs (if available)

Check if this feature is already implemented or planned.
If yes → STOP and notify user.

---

## Step 7 — Generate spec document

Use this structure:

---

# Spec: <feature_title>

## Overview

Explain what the feature does and why it is needed.

## Depends on

List prerequisite features or steps.

## Routes / APIs

List all new endpoints:

* METHOD /path — description — access level

If none: "No new routes"

## Database changes

* New tables / fields / indexes / constraints

If none: "No database changes"

## UI / Templates / Frontend

* Create: new UI components/pages
* Modify: existing UI changes

## Files to change

List all files that will be modified.

## Files to create

List all new files.

## New dependencies

List libraries/packages required.

If none: "No new dependencies"

## Rules for implementation

Include constraints such as:

* Follow project architecture
* Secure coding practices
* Input validation required
* Use environment variables for secrets
* No hardcoded credentials
* Reusable components preferred

(Add project-specific rules if applicable)

## Definition of done

Checklist:

* Feature works end-to-end
* No errors in logs
* UI behaves correctly
* Data persists correctly
* Edge cases handled
* Tested manually or via unit tests

---

## Step 8 — Save spec file

Save to:
docs/specs/<step_number>-<feature_slug>.md

(Create folder if it does not exist)

---

## Step 9 — Output summary

Print:

Branch:    <branch_name>
Spec file: docs/specs/<step_number>-<feature_slug>.md
Title:     <feature_title>

Then say:

"Review the spec at docs/specs/<step_number>-<feature_slug>.md
then proceed with implementation."

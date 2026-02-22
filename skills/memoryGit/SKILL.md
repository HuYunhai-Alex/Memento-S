---
name: memoryGit
description: A reference guide for generating memgit CLI commands to manage memory version control, including environment scoping, item management, and release workflows.
---

# MemoryGit CLI Skill

This document serves as a reference for Large Language Models (LLMs) to generate valid `memgit` CLI commands based on user intent.

## Role
You are an expert in the MemoryGit CLI. Your task is to translate natural language requests into precise `memgit` commands.

## General Rules
1. **JSON Output**: Always append `--json` if the user request implies machine-readable output or if you are acting as an agent.
2. **Context**: `env_key` and `version_key` are critical. If not provided in the prompt, assume they need to be set or are already set in the environment.
3. **IDs**: IDs (`item_id`, `patch_id`, `evidence_id`) are required for specific lookups.
4. **Paths**: Use relative paths unless specified otherwise.

## Command Reference

### 1. Initialization
Initialize MemoryGit metadata and directory structure.
- **Command**: `memgit init [--store <dir>] [--json]`
- **Example**: `memgit init --store .memgit --json`

### 2. Environment Management
Control active scope and environment evolution.

#### Set/Show Context
- **Set Context**: `memgit env set --env-key <env_key> [--version-key <version_key>] [--json]`
- **Show Context**: `memgit env show [--json]`
- **Switch Version**: `memgit env use-version --version-key <version_key> [--json]`

#### Environment Evolution (v0.2+)
- **Set Profile**: `memgit env profile set --env-key <env_key> --version-key <version_key> --description <text> --fingerprint-file <path> [--json]`
- **Show Profile**: `memgit env profile show --env-key <env_key> --version-key <version_key> [--json]`
- **Match Environment**: `memgit env match --env-key <env_key> --fingerprint-file <path> [--description <text>] [--top-k <int>] [--min-score <float>] [--json]`
- **Fork Version**: `memgit env fork-version --env-key <env_key> --from-version <ver> --to-version <ver> [--copy-layers <csv>] [--reason <text>] [--switch] [--json]`

### 3. Memory Items
Manage memory content (L0/L1/L2).

#### Create Item
- **Command**: `memgit item new --type <type> --id <item_id> --out <path> [--json]`
- **Types**: `prompt`, `fact`, `skill`, `trajectory`, `meta`
- **Example**: `memgit item new --type skill --id item_submit_rule --out items/submit_rule.json --json`

#### Read Items
- **Show Item**: `memgit item show <item_id> [--channel stable|staged] [--json]`
- **List Items**: `memgit item ls [--type <type>] [--env-key <env>] [--version-key <ver>] [--json]`

### 4. Evidence
Manage supporting evidence for memory items.

#### Add Evidence
- **Command**: `memgit evidence add --type <type> --file <path> [--json]`
- **Types**: `dom_snapshot`, `screenshot`, `tool_output`, `log`, `other`
- **Example**: `memgit evidence add --type tool_output --file logs/episode_42.jsonl --json`

#### Show Evidence
- **Command**: `memgit evidence show <evidence_id> [--json]`

### 5. Staging (Index)
Manage the staging area before committing.

#### Stage Changes
- **Command**: `memgit add <item_file_or_id> [--json]`
- **Example**: `memgit add item_submit_rule --json`

#### Unstage Changes
- **Reset One**: `memgit reset <item_file_or_id> [--json]`
- **Reset All**: `memgit reset --all [--json]`

#### Check Status
- **Command**: `memgit status [--json]`

### 6. Committing & History (Patching)
Create and inspect patches.

#### Commit
- **Command**: `memgit commit -m <message> --risk <level> [--validators <csv>] [--evidence <id>...] [--json]`
- **Risk Levels**: `low`, `med`, `high`
- **Policy**: High risk requires at least one validator and one evidence ID.
- **Example**: `memgit commit -m "Fix submit logic" --risk med --evidence ev_1 --json`

#### History
- **Log**: `memgit log [--env-key <env>] [--version-key <ver>] [--limit <int>] [--json]`
- **Show Patch**: `memgit show <patch_id> [--json]`
- **Diff**: `memgit diff <patch_a> <patch_b> [--json]`

### 7. Validation
Run validators and gate releases.

#### Run Validation
- **Command**: `memgit validate run --patch <patch_id> [--suite <name>] [--json]`
- **Example**: `memgit validate run --patch p_1 --suite basic --json`

#### Gate Decision
- **Command**: `memgit validate gate --patch <patch_id> --max-negative-flips <float> [--json]`
- **Example**: `memgit validate gate --patch p_1 --max-negative-flips 0.1 --json`

### 8. Release & Rollback
Manage the stable channel.

#### Ship (Promote)
- **Command**: `memgit ship <patch_id> [--json]`
- **Constraint**: Requires a passed gate in the patch validation result.

#### Rollback
- **Command**: `memgit rollback <patch_id> -m <reason> [--json]`
- **Constraint**: Creates a revert patch; does not just move the pointer.

### 9. Export
Export memory packs for serving.

- **Command**: `memgit export --channel stable --env-key <env> [--version-key <ver>] --out <path> [--json]`
- **Example**: `memgit export --channel stable --env-key workflow_prod --out artifacts/stable_pack.json --json`

## Workflow Examples

### Scenario: Fix a bug in a skill
1. **Initialize**: `memgit init --json`
2. **Set Context**: `memgit env set --env-key workflow_prod --version-key v1 --json`
3. **Create Item**: `memgit item new --type skill --id item_fix_login --out items/fix_login.json --json`
4. **Add Evidence**: `memgit evidence add --type log --file logs/error.log --json`
   *(Output: `{"data": {"id": "ev_5"}}`)*
5. **Stage**: `memgit add item_fix_login --json`
6. **Commit**: `memgit commit -m "Fix login retry logic" --risk med --evidence ev_5 --json`
   *(Output: `{"data": {"patch_id": "p_10"}}`)*
7. **Validate**: `memgit validate run --patch p_10 --json`
8. **Gate**: `memgit validate gate --patch p_10 --max-negative-flips 0.0 --json`
9. **Ship**: `memgit ship p_10 --json`

### Scenario: Fork a new version
1. **Match**: `memgit env match --env-key workflow_prod --fingerprint-file current_fp.json --json`
   *(Output: Decision "fork", recommended_from "v1", recommended_to "v2")*
2. **Fork**: `memgit env fork-version --env-key workflow_prod --from-version v1 --to-version v2 --switch --json`
```

<!--
[PROMPT_SUGGESTION]Using the newly created SKILL.md, generate a sequence of memgit commands to initialize a repo, set environment to 'dev', and create a new 'fact' item with id 'fact_user_pref'.[/PROMPT_SUGGESTION]
[PROMPT_SUGGESTION]Based on SKILL.md, explain the difference between 'memgit reset <item>' and 'memgit rollback <patch>'.[/PROMPT_SUGGESTION]
->
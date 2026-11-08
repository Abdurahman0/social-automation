# Task 03: "Skills" and "Repo" sections on the dashboard

Owner's request (2026-11-08): the website gets two new sections that a non-programmer understands at a glance.
All project laws in `CLAUDE.md` apply (UI law, completion law, secrets law, memory law).

## 1. Skills section ("Ko'nikmalar")
Shows the Claude skills installed for the Claude account this project uses (account 1, `~/.claude`).
- Sources to read (read-only, never modify them):
  - personal skills: `~/.claude/skills/**/SKILL.md` (including `synced/` folders),
  - project skills: `<repo>/.claude/skills/**/SKILL.md`,
  - plugin skills: plugins listed in `~/.claude/plugins/installed_plugins.json` → their `skills/**/SKILL.md`
    (and `commands/*.md` if a plugin has commands; show them as "buyruq").
- Parse each SKILL.md frontmatter: `name`, `description`. Show per skill a card: readable name (turn
  `caveman-commit` into "Caveman commit"), a short plain description (first sentence, full text on open),
  where it comes from as a friendly label ("Shaxsiy", "Loyiha", "Plagin: Caveman"), and how to call it
  (`/name`). Group by source, with counts and a search box. Skills this project's pipeline actually uses get a
  "Ishda ishlatiladi" badge (decide from the code; if none, say so honestly).
- Never show UUID folder names, raw file paths, JSON, or file contents other than name/description. If a
  SKILL.md is broken, skip it quietly (log it) instead of showing an error.
- Refresh on page open (cache ~60 s). Empty state if no skills: friendly text.

## 2. Repo section ("GitHub")
Explains what will be pushed to GitHub, in plain words.
- Connection card: is a GitHub remote connected? If not: "GitHub hali ulanmagan" + one line on what the owner
  must do (send a repo link). If yes: repo name (owner/name, not the URL with creds), branch, last push time,
  and "N ta o'zgarish hali yuklanmagan" (commits ahead of the remote).
- "Keyingi yuklashda ketadi": commits not yet pushed (message, time in Tashkent time, how many files) and
  uncommitted changes, with files grouped into friendly categories (Kod, Sayt, Hujjatlar, Testlar, Sozlamalar,
  Media/rasmlar) with counts; expandable to file names. Use short commit hash only if needed, never as a title.
- "Hech qachon yuklanmaydi" card: explains in words that tokens/passwords, OAuth files, the owner's voice
  recordings, logs and render outputs stay only on this computer (derive from `.gitignore`). Do NOT list secret
  file names or any of their contents; never read `.env` or `secrets/`.
- Recent history: last ~20 commits as a readable timeline.
- Use `git` via subprocess read-only commands only (`status --porcelain`, `log`, `rev-list`, `remote`); strip
  any credentials from remote URLs; never run fetch/push from the website.

## Done means
- Both sections in the existing hand-built frontend (same design language, Uzbek texts, dark/light), behind the
  existing login, with API endpoints in `socialauto/web/server.py` returning already-friendly data.
- pytest: skills parsing (personal/project/plugin, broken frontmatter skipped, name prettifying), repo API
  (no remote, ahead commits, categories, credential stripping, secrets never listed), auth required.
- Screenshots phone / tablet / desktop of both sections in `proof/`, no overflow or scroll bugs; update
  README and `proof/REPORT.md`. Commit in small steps.

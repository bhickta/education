# Himguru fork — upstream merge workflow

Fork: `bhickta/education` (fork of `frappe/education`)
Working branch: `himguru`
Pinned baseline: `61408d3da51833a4045b5506be61d47b3a0a8d70` (upstream `develop`, 2026-10-30, `v17.0.0-dev`)

## Remotes

| Remote     | URL                                          | Purpose                     |
| ---------- | -------------------------------------------- | --------------------------- |
| `origin`   | `git@github.com:bhickta/education.git`        | Owned fork (push here)      |
| `upstream` | `https://github.com/frappe/education.git`     | Read-only source of updates |

## Rules

- The app **must keep identifying as `education`**: package directory `education/`,
  `pyproject.toml` name `education`, and `education/hooks.py` `app_name = "education"`.
  Bench imports and existing site installs depend on this.
- `himguru` is the integration branch. Feature work branches from it and merges back.
- Never push to `upstream`. Never force-push `himguru` once deployed.
- Do not run migrations or deploy from this clone until the architecture audit lands.

## Routine upstream sync

```bash
cd /tmp/opencode/education-fork
git fetch upstream --prune
git switch himguru
git merge upstream/develop        # or: git rebase upstream/develop
# resolve conflicts, keeping Himguru customizations on top of upstream changes
git push origin himguru
```

After any sync, re-verify the identity invariants:

```bash
grep -n 'app_name' education/hooks.py
grep -n '^name' pyproject.toml
python -c "import education; print(education.__version__)"
```

## When upstream conflicts touch the schema

Stop and defer to the architecture audit. Do not hand-merge DocType schema changes
without the migration plan; resolve non-schema conflicts only.

## Baseline pin

If the deployed commit changes, retarget the baseline explicitly:

```bash
git fetch upstream
git switch himguru
git merge --ff-only <new-deployed-sha>   # only if himguru has no local commits yet
```

## Himguru divergences

Keep this list current so upstream merges are deliberate rather than accidental.
Each item names the upstream files most likely to conflict and the compatibility
rule that must survive the merge.

### Phase 2 — programme curriculum (`Program Course` restored)

Upstream commit `1f20710` retired the `Program Course` child table and replaced
`Program.courses` with `Course.program`. Himguru restores the child table because
a course can be offered by more than one programme and curriculum metadata
(category, weekly periods, sort order, programme-specific grade template) belongs
to the programme-course pair, not the course master.

| Area | Fork behaviour | Upstream merge rule |
| --- | --- | --- |
| `education/education/doctype/program_course/` | DocType restored with legacy `course`, `course_name`, `required` plus `category`, `sort_order`, `weekly_periods`, `grade_template`, `is_active`. | Never delete this doctype again. Resolve schema conflicts field-by-field. |
| `Program.courses` | Table field restored as the curriculum source, before the Connections tab. | Keep the field. Do not replace it with a `Course.program`-only model. |
| `Program.validate()` | Rejects duplicate courses, missing courses, and cross-company courses when the site has more than one Company. | Keep Himguru validation unless upstream provides equivalent validation. |
| `Course.program` | Still present and still written/read for legacy paths (Student Batch, Grade Book, Course Enrollment). | Never drop or rewrite `Course.program` during an upstream sync until the batch/enrollment phase lands. |
| Reads | `program_courses.py` prefers `Program.courses`, then legacy `tabProgram Course`, then `Course.program`. Programme progress/APIs use it. | Keep the fallback order in any refactor. |
| Migration | `education/patches/v17_0/restore_program_courses.py` is additive and idempotent; it never deletes legacy rows and never changes `Course.program`. | Do not renumber or remove the patch after deployment. Append follow-up patches instead. |

Phase 2 does **not** change Student Batch or Course Enrollment semantics. Their
program fields continue to follow `Course.program`; the batch/enrollment
migration is the next phase.

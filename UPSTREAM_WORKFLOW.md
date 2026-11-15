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

### Phase 3 — batch and enrollment semantics

A programme can offer many courses, so a batch belongs to a programme and no
longer to a single course. Course Enrollment carries its own programme and
academic year. The legacy course links stay readable for existing records but
are no longer required or used to derive the programme.

| Area | Fork behaviour | Upstream merge rule |
| --- | --- | --- |
| `Student Batch Name.program` | Required, editable Link to `Program`; never fetched from `Course`. | Keep it independent of `Course.program`. |
| `Student Batch Name.course` | Optional and deprecated. A batch can cover any course in its programme curriculum. | Do not make it required again. |
| `Student Batch Name.academic_year` | Standard fork field, used by the legacy group migration. | Keep it; it is not a custom field. |
| `Student Batch Name.company` | Defaulted on single-company sites and hidden by the form when only one Company exists. | Keep `Company` consistency validation on multi-company sites. |
| `Student Batch Name.validate()` | Requires the programme, accepts a blank course, checks `(program, course)` through `Program Course`, and validates dates, capacity and company. | Keep these checks if upstream adds its own batch validation. |
| `Course Enrollment.program` | Explicit required Link, editable, never overwritten from `Course.program`. | Never restore `fetch_from`/`read_only` or a blanking `set_program_from_course()`. |
| `Course Enrollment.academic_year` | Standard Link field, fetched from the Admission Register when blank and required for new records. | Keep the field; do not rely on a site custom field. |
| Course Enrollment validation | `(program, course)` must be in `Program Course`; a batch must have the same programme; a legacy batch course must match; capacity, admission register and fee term checks stay. | Preserve all existing checks. |
| Programme default | Filled only when exactly one programme offers the course (`get_program_for_course`). Ambiguous courses require an explicit choice. | Keep the conservative default; never guess among multiple programmes. |
| `Subject Schedule` / `Assessment Plan` | Add a read-only `program` derived from the batch. `course` is chosen by the user, not fetched from `student_batch.course`, and must be in the programme curriculum. | Keep the derived programme and curriculum check through upstream schema changes. |
| Migration | `education/patches/v17_0/migrate_batches_and_enrollments.py` creates/normalises batches from legacy `Student Group`, backfills blank enrollment batch/programme/year from `Program Enrollment`/`Student Group`, and corrects a historical year only when the stored year cannot contain the enrollment date. | Append follow-up patches; do not renumber or remove the patch after deployment. |

Migration assumptions:

- It never submits Course Enrollments, creates fees, or deletes or rewrites
  legacy `Student Group` / `Program Enrollment` rows.
- Existing programme, batch, academic year, company and capacity values are
  kept. Only blank fields are filled.
- Legacy tables and columns are detected individually, so the patch is a no-op
  on sites without those tables and on partially migrated databases.
- `run(dry_run=True)` returns the planned counts without writing.
- A batch is created from a legacy group only when the group has a programme,
  a company (explicit or the single default Company) and an academic year with
  start/end dates. Ambiguous academic years or companies are skipped.
- `Student Group` rows linked to an existing `batch` normalise that batch;
  other rows use the group name. Existing batches are never renamed.
- The patch is idempotent: a second run finds no blank fields to fill.

Tests live in `test_student_batch_name.py` and `test_course_enrollment.py` and
cover the schema contract, conservative programme defaults, batch planning, and
academic-year backfill helpers.

Still deferred to Phase 4/5: dropping `Course.program`, removing Himguru custom
fields, rewriting Grade Book programme handling, reworking the Subject
Scheduling Tool and Student Attendance Tool for multi-course batches, and any
data cleanup that requires a destructive migration.

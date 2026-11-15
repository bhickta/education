# Copyright (c) 2026, Himguru and contributors
# For license information, please see license.txt

"""Run the Phase 3 batch and Course Enrollment compatibility migration."""

from __future__ import annotations

from education.education.batch_enrollment_migration import run


def execute():
	return run()

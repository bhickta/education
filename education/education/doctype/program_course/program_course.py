# Copyright (c) 2015, Frappe Technologies and contributors
# For license information, please see license.txt


from frappe.model.document import Document


class ProgramCourse(Document):
	# Curriculum rows are validated on the Program parent: duplicate courses,
	# course existence and company consistency all need the full programme.
	pass

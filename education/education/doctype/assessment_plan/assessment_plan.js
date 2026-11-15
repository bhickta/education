// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Assessment Plan', {
  onload: function (frm) {
    frm.set_query('assessment_group', function (doc, cdt, cdn) {
      return {
        filters: {
          is_group: 0,
        },
      }
    })
    frm.set_query('subject', function () {
      return {
        filters: {
          course: frm.doc.course,
        },
      }
    })
    frm.set_query('course', function () {
      if (!frm.doc.program) return {}
      return {
        query:
          'education.education.doctype.program.program.get_program_courses',
        filters: {
          program: frm.doc.program,
        },
      }
    })
    set_academic_queries(frm)
    set_room_query(frm)
    set_default_academic_year(frm)
  },

  refresh: function (frm) {
    if (frm.doc.docstatus == 1) {
      frm.add_custom_button(__('Statistics'), function () {
        frappe.set_route('query-report', 'Assessment Statistics', {
          assessment_plan: frm.doc.name,
        })
      })

      frm.add_custom_button(
        __('Assessment Result Tool'),
        function () {
          frappe.route_options = {
            assessment_plan: frm.doc.name,
            student_batch: frm.doc.student_batch,
          }
          frappe.set_route('Form', 'Assessment Result Tool')
        },
        __('Tools')
      )
    }

    set_academic_queries(frm)
    set_room_query(frm)
    set_default_academic_year(frm)
  },

  student_batch: function (frm) {
    if (frm.doc.subject) {
      frm.set_value('subject', '')
    }
    frm.set_value('course', null)

    if (!frm.doc.student_batch) return

    frappe.db
      .get_value('Student Batch Name', frm.doc.student_batch, [
        'program',
        'course',
      ])
      .then((r) => {
        const batch = r.message || {}
        frm.set_value('program', batch.program || null)
        if (batch.course) {
          frm.set_value('course', batch.course)
        }
      })
  },

  company: function (frm) {
    set_academic_queries(frm)
  },

  academic_year: function (frm) {
    if (frm.doc.academic_term) {
      frm.set_value('academic_term', '')
    }
    set_academic_queries(frm)
  },

  course: function (frm) {
    if (frm.doc.subject) {
      frm.set_value('subject', '')
    }
  },

  campus(frm) {
    if (!frm.doc.room || !frm.doc.campus) {
      return
    }
    frappe.db.get_value('Room', frm.doc.room, 'campus').then((r) => {
      const room_campus = r && r.message && r.message.campus
      if (room_campus && room_campus !== frm.doc.campus) {
        frm.set_value('room', '')
      }
    })
  },
})

function set_default_academic_year(frm) {
  if (!frm.is_new() || frm.doc.academic_year) {
    return
  }
  const year = frappe.defaults.get_user_default('academic_year')
  if (year) {
    frm.set_value('academic_year', year)
  }
}

function set_room_query(frm) {
  frm.set_query('room', () => ({
    query: 'education.education.doctype.room.room.room_query',
    filters: {
      campus: frm.doc.campus,
    },
  }))
}

function set_academic_queries(frm) {
  frm.set_query('academic_year', function () {
    const filters = {}
    if (frm.doc.company) {
      filters.company = frm.doc.company
    }
    return { filters }
  })

  frm.set_query('academic_term', function () {
    const filters = {}
    if (frm.doc.academic_year) {
      filters.academic_year = frm.doc.academic_year
    }
    if (frm.doc.company) {
      filters.company = frm.doc.company
    }
    return { filters }
  })
}

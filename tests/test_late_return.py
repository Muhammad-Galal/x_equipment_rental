from datetime import timedelta

from odoo import fields

from .common import RentalCommon


class TestLateReturn(RentalCommon):
    def test_cron_marks_overdue_and_computes_late_fee(self):
        today = fields.Date.today()
        start_date = today - timedelta(days=5)
        end_date = today - timedelta(days=2)
        order = self._create_order(self.equipment_1 | self.equipment_2, start_date, end_date)
        order.action_confirm()
        order.action_mark_out()

        order.write(
            {
                "is_overdue": False,
                "overdue_days": 0,
                "late_fee_amount": 0.0,
            }
        )
        self.env["x.rental.order"]._cron_update_overdue_rentals()
        order.invalidate_recordset(["is_overdue", "overdue_days", "late_fee_amount"])

        self.assertTrue(order.is_overdue)
        self.assertEqual(order.overdue_days, 2)
        self.assertEqual(order.late_fee_amount, 40.0)

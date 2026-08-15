from datetime import timedelta

from odoo import fields

from .common import RentalCommon


class TestRentalPricing(RentalCommon):
    def test_daily_rate_for_short_rental(self):
        start_date = fields.Date.today() + timedelta(days=10)
        end_date = start_date + timedelta(days=2)
        order = self._create_order(self.equipment_1, start_date, end_date)

        self.assertEqual(order.duration_days, 3)
        self.assertEqual(order.line_ids.duration_days, 3)
        self.assertEqual(order.line_ids.pricing_type, "daily")
        self.assertEqual(order.line_ids.price_subtotal, 300.0)
        self.assertEqual(order.amount_total, 300.0)

    def test_weekly_rate_for_exact_week(self):
        start_date = fields.Date.today() + timedelta(days=20)
        end_date = start_date + timedelta(days=6)
        order = self._create_order(self.equipment_1, start_date, end_date)

        self.assertEqual(order.duration_days, 7)
        self.assertEqual(order.line_ids.pricing_type, "weekly")
        self.assertEqual(order.line_ids.price_subtotal, 600.0)

    def test_mixed_rate_for_partial_extra_days(self):
        start_date = fields.Date.today() + timedelta(days=30)
        end_date = start_date + timedelta(days=8)
        order = self._create_order(self.equipment_1, start_date, end_date)

        self.assertEqual(order.duration_days, 9)
        self.assertEqual(order.line_ids.pricing_type, "mixed")
        self.assertEqual(order.line_ids.price_subtotal, 800.0)

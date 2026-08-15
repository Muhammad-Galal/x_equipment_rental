from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class RentalCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.partner = cls.env["res.partner"].create({"name": "Rental Customer"})
        cls.category = cls.env["maintenance.equipment.category"].create(
            {
                "name": "Heavy Equipment",
                "company_id": cls.company.id,
            }
        )
        cls.team = cls.env["maintenance.team"].create(
            {
                "name": "Rental Maintenance Team",
                "company_id": cls.company.id,
            }
        )
        cls.rental_product = cls.env.ref(
            "x_equipment_rental.product_rental_service_template"
        ).product_variant_id
        cls.env["ir.config_parameter"].sudo().set_param(
            "x_equipment_rental.rental_service_product_id", cls.rental_product.id
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "x_equipment_rental.rental_sale_integration_mode", "sale_order"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "x_equipment_rental.rental_late_fee_per_day", 10.0
        )

        cls.equipment_1 = cls.env["maintenance.equipment"].create(
            {
                "name": "Excavator A",
                "category_id": cls.category.id,
                "company_id": cls.company.id,
                "maintenance_team_id": cls.team.id,
                "serial_no": "EXC-A-001",
                "effective_date": fields.Date.to_string(fields.Date.today() - timedelta(days=60)),
                "daily_rental_rate": 100.0,
                "weekly_rental_rate": 600.0,
            }
        )
        cls.equipment_2 = cls.env["maintenance.equipment"].create(
            {
                "name": "Excavator B",
                "category_id": cls.category.id,
                "company_id": cls.company.id,
                "maintenance_team_id": cls.team.id,
                "serial_no": "EXC-B-001",
                "effective_date": fields.Date.to_string(fields.Date.today() - timedelta(days=45)),
                "daily_rental_rate": 120.0,
                "weekly_rental_rate": 700.0,
            }
        )

        rental_user_group = cls.env.ref("x_equipment_rental.group_rental_user")
        rental_manager_group = cls.env.ref("x_equipment_rental.group_rental_manager")
        cls.rental_user = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Rental User",
                "login": "rental_user",
                "email": "rental_user@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "group_ids": [(6, 0, [rental_user_group.id])],
            }
        )
        cls.rental_manager = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Rental Manager",
                "login": "rental_manager",
                "email": "rental_manager@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "group_ids": [(6, 0, [rental_manager_group.id])],
            }
        )

    def _create_order(self, equipment, start_date, end_date, **extra_vals):
        equipment_records = equipment if hasattr(equipment, "ids") else self.env["maintenance.equipment"].browse(equipment)
        vals = {
            "partner_id": self.partner.id,
            "user_id": self.env.user.id,
            "company_id": self.company.id,
            "rental_start_date": start_date,
            "rental_end_date": end_date,
            "line_ids": [(0, 0, {"equipment_id": record.id}) for record in equipment_records],
        }
        vals.update(extra_vals)
        return self.env["x.rental.order"].create(vals)

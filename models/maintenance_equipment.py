from datetime import datetime, time

from odoo import _, api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
        string="Currency",
    )
    daily_rental_rate = fields.Monetary(
        string="Daily Rental Rate",
        currency_field="currency_id",
        tracking=True,
    )
    weekly_rental_rate = fields.Monetary(
        string="Weekly Rental Rate",
        currency_field="currency_id",
        tracking=True,
    )
    rental_status = fields.Selection(
        [
            ("available", "Available"),
            ("reserved", "Reserved"),
            ("rented", "Rented"),
            ("maintenance", "Maintenance"),
        ],
        compute="_compute_rental_status",
        search="_search_rental_status",
        string="Rental Status",
    )
    rental_order_line_ids = fields.One2many(
        "x.rental.order.line",
        "equipment_id",
        string="Rental Lines",
    )
    rental_maintenance_ids = fields.One2many(
        "maintenance.request",
        "equipment_id",
        string="Maintenance Requests",
    )
    rental_order_count = fields.Integer(
        compute="_compute_rental_order_count",
        string="Rental Orders",
    )
    rental_maintenance_count = fields.Integer(
        compute="_compute_rental_maintenance_count",
        string="Maintenance Count",
    )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for equipment in self:
            equipment.currency_id = equipment.company_id.currency_id or self.env.company.currency_id

    @api.depends(
        "rental_order_line_ids.state",
        "rental_maintenance_ids.schedule_date",
        "rental_maintenance_ids.schedule_end",
        "rental_maintenance_ids.done",
        "rental_maintenance_ids.archive",
    )
    def _compute_rental_status(self):
        today = fields.Date.context_today(self)
        maintenance_records = self.env["maintenance.request"].search(
            self._get_maintenance_overlap_domain(today, today, equipment_ids=self.ids)
        )
        out_lines = self.env["x.rental.order.line"].search([
            ("equipment_id", "in", self.ids),
            ("state", "=", "out"),
            ("rental_start_date", "<=", today),
            ("rental_end_date", ">=", today),
        ])
        confirmed_lines = self.env["x.rental.order.line"].search([
            ("equipment_id", "in", self.ids),
            ("state", "=", "confirmed"),
            ("rental_end_date", ">=", today),
        ])
        maintenance_ids = set(maintenance_records.mapped("equipment_id").ids)
        rented_ids = set(out_lines.mapped("equipment_id").ids)
        reserved_ids = set(confirmed_lines.mapped("equipment_id").ids)
        for equipment in self:
            if equipment.id in maintenance_ids:
                equipment.rental_status = "maintenance"
            elif equipment.id in rented_ids:
                equipment.rental_status = "rented"
            elif equipment.id in reserved_ids:
                equipment.rental_status = "reserved"
            else:
                equipment.rental_status = "available"

    def _compute_rental_order_count(self):
        grouped_data = self.env["x.rental.order.line"]._read_group(
            [("equipment_id", "in", self.ids)],
            ["equipment_id"],
            ["__count"],
        )
        count_by_equipment = {equipment.id: count for equipment, count in grouped_data}
        for equipment in self:
            equipment.rental_order_count = count_by_equipment.get(equipment.id, 0)

    def _compute_rental_maintenance_count(self):
        grouped_data = self.env["maintenance.request"]._read_group(
            [("equipment_id", "in", self.ids)],
            ["equipment_id"],
            ["__count"],
        )
        count_by_equipment = {equipment.id: count for equipment, count in grouped_data}
        for equipment in self:
            equipment.rental_maintenance_count = count_by_equipment.get(equipment.id, 0)

    @api.model
    def _search_rental_status(self, operator, value):
        if operator not in ("=", "!=") or value not in {"available", "reserved", "rented", "maintenance"}:
            return [("id", "=", 0)]

        today = fields.Date.context_today(self)
        maintenance_ids = set(
            self.env["maintenance.request"].search(
                self._get_maintenance_overlap_domain(today, today)
            ).mapped("equipment_id").ids
        )
        rented_ids = set(
            self.env["x.rental.order.line"].search([
                ("state", "=", "out"),
                ("rental_start_date", "<=", today),
                ("rental_end_date", ">=", today),
            ]).mapped("equipment_id").ids
        )
        reserved_ids = set(
            self.env["x.rental.order.line"].search([
                ("state", "=", "confirmed"),
                ("rental_end_date", ">=", today),
            ]).mapped("equipment_id").ids
        )
        status_map = {
            "maintenance": maintenance_ids,
            "rented": rented_ids - maintenance_ids,
            "reserved": reserved_ids - rented_ids - maintenance_ids,
            "available": set(),
        }
        if value == "available":
            domain = [("id", "not in", list(maintenance_ids | rented_ids | reserved_ids))]
        else:
            domain = [("id", "in", list(status_map[value]))]
        return domain if operator == "=" else [("id", "not in" if domain[0][1] == "in" else "in", domain[0][2])]

    @api.model
    def _get_maintenance_overlap_domain(
        self,
        start_date,
        end_date,
        company_id=False,
        equipment_ids=None,
        excluded_request_ids=None,
    ):
        start_dt = fields.Datetime.to_string(datetime.combine(start_date, time.min))
        end_dt = fields.Datetime.to_string(datetime.combine(end_date, time.max))
        domain = [
            ("equipment_id", "!=", False),
            ("archive", "=", False),
            ("done", "=", False),
            ("schedule_date", "!=", False),
            ("schedule_end", "!=", False),
            ("schedule_date", "<=", end_dt),
            ("schedule_end", ">=", start_dt),
        ]
        if company_id:
            domain.append(("company_id", "=", company_id))
        if equipment_ids:
            domain.append(("equipment_id", "in", equipment_ids))
        if excluded_request_ids:
            domain.append(("id", "not in", excluded_request_ids))
        return domain

    @api.model
    def _get_unavailable_equipment_ids(
        self,
        start_date,
        end_date,
        company_id=False,
        excluded_rental_line_ids=None,
        excluded_maintenance_ids=None,
        rental_states=None,
        maintenance_states=None,
    ):
        del maintenance_states
        rental_states = rental_states or ["confirmed", "out"]
        unavailable_ids = set()
        rental_domain = [
            ("rental_start_date", "<=", end_date),
            ("rental_end_date", ">=", start_date),
            ("state", "in", rental_states),
        ]
        if company_id:
            rental_domain.append(("company_id", "=", company_id))
        if excluded_rental_line_ids:
            rental_domain.append(("id", "not in", excluded_rental_line_ids))

        rental_lines = self.env["x.rental.order.line"].search(rental_domain)
        maintenance_records = self.env["maintenance.request"].search(
            self._get_maintenance_overlap_domain(
                start_date,
                end_date,
                company_id=company_id,
                excluded_request_ids=excluded_maintenance_ids,
            )
        )
        unavailable_ids.update(rental_lines.mapped("equipment_id").ids)
        unavailable_ids.update(maintenance_records.mapped("equipment_id").ids)
        return list(unavailable_ids)

    def action_view_rental_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "x_equipment_rental.action_rental_order"
        )
        action["domain"] = [("line_ids.equipment_id", "=", self.id)]
        action["context"] = {
            "default_line_ids": [
                (
                    0,
                    0,
                    {
                        "equipment_id": self.id,
                        "daily_rate": self.daily_rental_rate,
                        "weekly_rate": self.weekly_rental_rate,
                    },
                )
            ],
        }
        return action

    def action_view_rental_maintenance(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "x_equipment_rental.action_equipment_maintenance"
        )
        action["domain"] = [("equipment_id", "=", self.id)]
        action["context"] = {
            "default_equipment_id": self.id,
            "default_owner_user_id": self.env.user.id,
        }
        return action

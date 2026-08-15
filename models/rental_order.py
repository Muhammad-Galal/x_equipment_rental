from odoo import _, api, fields, models
from odoo.exceptions import LockError, UserError, ValidationError


class RentalOrder(models.Model):
    _name = "x.rental.order"
    _description = "Equipment Rental Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "rental_start_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        tracking=True,
        check_company=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    rental_start_date = fields.Date(required=True, tracking=True)
    rental_end_date = fields.Date(required=True, tracking=True)
    duration_days = fields.Integer(
        compute="_compute_duration_days",
        store=True,
    )
    line_ids = fields.One2many(
        "x.rental.order.line",
        "order_id",
        string="Equipment Lines",
        copy=True,
    )
    equipment_count = fields.Integer(
        compute="_compute_equipment_count",
    )
    amount_total = fields.Monetary(
        compute="_compute_amount_total",
        currency_field="currency_id",
        store=True,
    )
    actual_return_date = fields.Date(
        readonly=True,
        copy=False,
        tracking=True,
    )
    is_overdue = fields.Boolean(
        readonly=True,
        copy=False,
        tracking=True,
    )
    overdue_days = fields.Integer(
        readonly=True,
        copy=False,
    )
    late_fee_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        copy=False,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("out", "Out"),
            ("returned", "Returned"),
            ("invoiced", "Invoiced"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        readonly=True,
        copy=False,
    )
    account_move_id = fields.Many2one(
        "account.move",
        readonly=True,
        copy=False,
    )
    note = fields.Html()

    _active_booking_states = ("confirmed", "out")

    @api.depends("rental_start_date", "rental_end_date")
    def _compute_duration_days(self):
        for order in self:
            if order.rental_start_date and order.rental_end_date:
                order.duration_days = (order.rental_end_date - order.rental_start_date).days + 1
            else:
                order.duration_days = 0

    @api.depends("line_ids")
    def _compute_equipment_count(self):
        for order in self:
            order.equipment_count = len(order.line_ids)

    @api.depends("line_ids.price_subtotal")
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(order.line_ids.mapped("price_subtotal"))

    @api.constrains("rental_start_date", "rental_end_date")
    def _check_date_range(self):
        for order in self:
            if (
                order.rental_start_date
                and order.rental_end_date
                and order.rental_end_date < order.rental_start_date
            ):
                raise ValidationError(_("The rental end date must be on or after the start date."))

    @api.constrains("line_ids", "state")
    def _check_required_lines(self):
        for order in self:
            if order.state in self._active_booking_states and not order.line_ids:
                raise ValidationError(_("A rental order must contain at least one equipment line."))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = sequence.next_by_code("x.rental.order") or _("New")
        return super().create(vals_list)

    def _check_can_confirm(self):
        for order in self:
            if order.state != "draft":
                raise UserError(_("Only draft rental orders can be confirmed."))
            if not order.line_ids:
                raise ValidationError(_("Add at least one equipment line before confirming the rental order."))

    def _check_can_mark_out(self):
        for order in self:
            if order.state != "confirmed":
                raise UserError(_("Only confirmed rental orders can be marked as Out."))

    def _check_can_return(self):
        for order in self:
            if order.state != "out":
                raise UserError(_("Only rental orders in Out state can be returned."))

    def _check_can_invoice(self):
        for order in self:
            if order.state != "returned":
                raise UserError(_("Only returned rental orders can be marked as invoiced."))

    def _check_can_cancel(self):
        for order in self:
            if order.state not in ("draft", "confirmed"):
                raise UserError(_("Rental orders can only be cancelled from Draft or Confirmed state."))

    def _lock_equipment_for_confirmation(self):
        equipment = self.line_ids.mapped("equipment_id").sorted("id")
        if not equipment:
            return
        try:
            equipment.lock_for_update()
        except LockError as err:
            raise ValidationError(
                _("Some equipment records are being booked by another transaction. Please retry.")
            ) from err

    def action_confirm(self):
        self._check_can_confirm()
        self._lock_equipment_for_confirmation()
        # Re-check inside the equipment lock to cover concurrent confirmations.
        self.line_ids._raise_booking_conflicts(forced_state="confirmed")
        self.write({"state": "confirmed"})
        self._apply_overdue_status()
        self._generate_sales_documents()

    def action_mark_out(self):
        self._check_can_mark_out()
        self.write({"state": "out"})
        self._apply_overdue_status()

    def action_return(self):
        self._check_can_return()
        return_date = fields.Date.context_today(self)
        self.write({"state": "returned", "actual_return_date": return_date})
        self._apply_overdue_status(reference_date=return_date, include_returned=True)

    def action_mark_invoiced(self):
        self._check_can_invoice()
        self.write({"state": "invoiced"})

    def action_cancel(self):
        self._check_can_cancel()
        self.write({"state": "cancelled"})
        self._clear_overdue_status()

    @api.model
    def _get_late_fee_per_day(self):
        return float(
            self.env["ir.config_parameter"].sudo().get_param(
                "x_equipment_rental.rental_late_fee_per_day", 0.0
            )
            or 0.0
        )

    def _compute_overdue_values(self, reference_date):
        self.ensure_one()
        if not self.rental_end_date:
            return {"is_overdue": False, "overdue_days": 0, "late_fee_amount": 0.0}
        overdue_days = max((reference_date - self.rental_end_date).days, 0)
        late_fee_per_day = self._get_late_fee_per_day()
        line_count = max(len(self.line_ids), 1)
        return {
            "is_overdue": overdue_days > 0,
            "overdue_days": overdue_days,
            "late_fee_amount": overdue_days * late_fee_per_day * line_count,
        }

    def _apply_overdue_status(self, reference_date=None, include_returned=False):
        reference_date = reference_date or fields.Date.context_today(self)
        eligible_states = set(self._active_booking_states)
        if include_returned:
            eligible_states.add("returned")
        for order in self:
            if order.state not in eligible_states:
                continue
            values = order._compute_overdue_values(reference_date)
            order.write(values)

    def _clear_overdue_status(self):
        self.write(
            {
                "is_overdue": False,
                "overdue_days": 0,
                "late_fee_amount": 0.0,
                "actual_return_date": False,
            }
        )

    @api.model
    def _cron_update_overdue_rentals(self):
        today = fields.Date.context_today(self)
        active_orders = self.search([("state", "in", list(self._active_booking_states))])
        active_orders._apply_overdue_status(reference_date=today)

    def _get_rental_service_product(self):
        self.ensure_one()
        product_id = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "x_equipment_rental.rental_service_product_id", 0
            )
            or 0
        )
        product = self.env["product.product"].browse(product_id).exists()
        if not product:
            template = self.env.ref(
                "x_equipment_rental.product_rental_service_template",
                raise_if_not_found=False,
            )
            product = template.product_variant_id if template else False
        if not product:
            raise UserError(
                _(
                    "Configure a rental service product in Settings before confirming rental orders."
                )
            )
        return product

    def _prepare_billing_line_name(self, line):
        pricing_label = {
            "daily": _("Daily"),
            "weekly": _("Weekly"),
            "mixed": _("Weekly + Daily"),
        }.get(line.pricing_type, _("Rental"))
        return _(
            "%(equipment)s\nRental Period: %(start)s to %(end)s\nPricing: %(pricing)s",
            equipment=line.equipment_id.display_name,
            start=line.rental_start_date,
            end=line.rental_end_date,
            pricing=pricing_label,
        )

    def _prepare_sale_order_vals(self):
        self.ensure_one()
        product = self._get_rental_service_product()
        order_lines = []
        for line in self.line_ids:
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": self._prepare_billing_line_name(line),
                        "product_uom_qty": 1.0,
                        "price_unit": line.price_subtotal,
                    },
                )
            )
        return {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "origin": self.name,
            "client_order_ref": self.name,
            "order_line": order_lines,
        }

    def _prepare_invoice_vals(self):
        self.ensure_one()
        product = self._get_rental_service_product()
        invoice_lines = []
        for line in self.line_ids:
            invoice_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": self._prepare_billing_line_name(line),
                        "quantity": 1.0,
                        "price_unit": line.price_subtotal,
                        "tax_ids": [(6, 0, product.taxes_id.ids)],
                    },
                )
            )
        return {
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "invoice_origin": self.name,
            "invoice_user_id": self.user_id.id,
            "invoice_line_ids": invoice_lines,
        }

    def _generate_sales_documents(self):
        sale_order_model = self.env["sale.order"]
        account_move_model = self.env["account.move"]
        for order in self:
            if order.sale_order_id or order.account_move_id:
                continue
            mode = self.env["ir.config_parameter"].sudo().get_param(
                "x_equipment_rental.rental_sale_integration_mode", "sale_order"
            )
            if mode == "sale_order":
                sale_order = sale_order_model.create(order._prepare_sale_order_vals())
                sale_order.action_confirm()
                order.sale_order_id = sale_order
            elif mode == "customer_invoice":
                invoice = account_move_model.create(order._prepare_invoice_vals())
                order.account_move_id = invoice

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("No sales order has been generated for this rental order."))
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_orders")
        action["views"] = [(False, "form")]
        action["res_id"] = self.sale_order_id.id
        return action

    def action_view_invoice(self):
        self.ensure_one()
        if not self.account_move_id:
            raise UserError(_("No customer invoice has been generated for this rental order."))
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action["views"] = [(False, "form")]
        action["res_id"] = self.account_move_id.id
        return action


class RentalOrderLine(models.Model):
    _name = "x.rental.order.line"
    _description = "Equipment Rental Order Line"
    _order = "id"
    _check_company_auto = True

    order_id = fields.Many2one(
        "x.rental.order",
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(
        related="order_id.state",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="order_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="order_id.currency_id",
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="order_id.partner_id",
        store=True,
        readonly=True,
    )
    rental_start_date = fields.Date(
        related="order_id.rental_start_date",
        store=True,
        readonly=True,
    )
    rental_end_date = fields.Date(
        related="order_id.rental_end_date",
        store=True,
        readonly=True,
    )
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    category_id = fields.Many2one(
        related="equipment_id.category_id",
        store=True,
        readonly=True,
        string="Equipment Category",
    )
    name = fields.Char(
        string='Description',
        related='equipment_id.name',
        store=True,
        readonly=True,
    )
    daily_rate = fields.Monetary(
        required=True,
        currency_field="currency_id",
    )
    weekly_rate = fields.Monetary(
        required=True,
        currency_field="currency_id",
    )
    duration_days = fields.Integer(
        compute="_compute_duration_days",
        store=True,
    )
    pricing_type = fields.Selection(
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("mixed", "Weekly + Daily"),
        ],
        compute="_compute_pricing",
        store=True,
    )
    price_subtotal = fields.Monetary(
        compute="_compute_pricing",
        currency_field="currency_id",
        store=True,
    )

    _sql_constraints = [
        (
            "x_rental_order_line_equipment_unique",
            "unique(order_id, equipment_id)",
            "The same equipment cannot be added twice to the same rental order.",
        ),
    ]


    @api.depends("rental_start_date", "rental_end_date")
    def _compute_duration_days(self):
        for line in self:
            if line.rental_start_date and line.rental_end_date:
                line.duration_days = (line.rental_end_date - line.rental_start_date).days + 1
            else:
                line.duration_days = 0

    @api.depends("duration_days", "daily_rate", "weekly_rate")
    def _compute_pricing(self):
        for line in self:
            if not line.duration_days:
                line.pricing_type = "daily"
                line.price_subtotal = 0.0
                continue
            if line.duration_days < 7:
                line.pricing_type = "daily"
                line.price_subtotal = line.daily_rate * line.duration_days
                continue
            weeks, extra_days = divmod(line.duration_days, 7)
            line.pricing_type = "weekly" if not extra_days else "mixed"
            line.price_subtotal = (weeks * line.weekly_rate) + (extra_days * line.daily_rate)

    @api.onchange("equipment_id")
    def _onchange_equipment_id(self):
        for line in self:
            if line.equipment_id:
                line.daily_rate = line.equipment_id.daily_rental_rate
                line.weekly_rate = line.equipment_id.weekly_rental_rate

    @api.model_create_multi
    def create(self, vals_list):
        equipment_model = self.env["maintenance.equipment"]
        for vals in vals_list:
            if vals.get("equipment_id"):
                equipment = equipment_model.browse(vals["equipment_id"])
                vals.setdefault("daily_rate", equipment.daily_rental_rate)
                vals.setdefault("weekly_rate", equipment.weekly_rental_rate)
        return super().create(vals_list)

    @api.constrains("equipment_id", "rental_start_date", "rental_end_date", "state")
    def _check_booking_conflicts(self):
        self._raise_booking_conflicts()

    def _raise_booking_conflicts(self, forced_state=None):
        active_lines = self.filtered(lambda line: line.equipment_id and line.rental_start_date and line.rental_end_date)
        if not active_lines:
            return

        equipment_model = self.env["maintenance.equipment"]
        for line in active_lines:
            effective_state = forced_state or line.state
            if effective_state not in RentalOrder._active_booking_states:
                continue
            overlapping_line = self.search(
                [
                    ("id", "!=", line.id),
                    ("equipment_id", "=", line.equipment_id.id),
                    ("state", "in", RentalOrder._active_booking_states),
                    ("rental_start_date", "<=", line.rental_end_date),
                    ("rental_end_date", ">=", line.rental_start_date),
                ],
                limit=1,
            )
            if overlapping_line:
                raise ValidationError(
                    _(
                        "Equipment %(equipment)s is already booked on rental order %(order)s during the selected period.",
                        equipment=line.equipment_id.display_name,
                        order=overlapping_line.order_id.display_name,
                    )
                )

            maintenance_conflict = self.env["maintenance.request"].search(
                equipment_model._get_maintenance_overlap_domain(
                    line.rental_start_date,
                    line.rental_end_date,
                    company_id=line.company_id.id,
                    equipment_ids=line.equipment_id.ids,
                ),
                limit=1,
            )
            if maintenance_conflict:
                raise ValidationError(
                    _(
                        "Equipment %(equipment)s is scheduled for maintenance in the selected rental period.",
                        equipment=line.equipment_id.display_name,
                    )
                )

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = sequence.next_by_code("x.rental.order") or _("New")
        return super().create(vals_list)


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
        required=True,
        compute="_compute_name",
        store=True,
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

    @api.depends("equipment_id", "rental_start_date", "rental_end_date")
    def _compute_name(self):
        for line in self:
            equipment_name = line.equipment_id.display_name or _("Equipment")
            if line.rental_start_date and line.rental_end_date:
                line.name = _(
                    "%(equipment)s (%(start)s to %(end)s)",
                    equipment=equipment_name,
                    start=line.rental_start_date,
                    end=line.rental_end_date,
                )
            else:
                line.name = equipment_name

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

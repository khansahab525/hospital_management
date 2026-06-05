from odoo import api, fields, models


class HospitalHomeContent(models.Model):
    _name = "hospital.home.content"
    _description = "Hospital Home Page Content"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_published = fields.Boolean(default=False, tracking=True, copy=False)
    published_date = fields.Datetime(readonly=True, copy=False)
    published_by_id = fields.Many2one("res.users", readonly=True, copy=False)

    section_type = fields.Selection(
        [
            ("header", "Website Header"),
            ("footer", "Website Footer"),
            ("hero", "Hero Banner"),
            ("content", "Content Block"),
            ("feature", "Feature Card"),
            ("cta", "Call To Action"),
            ("stats", "Statistics"),
        ],
        required=True,
        default="content",
        tracking=True,
    )
    layout = fields.Selection(
        [
            ("text_only", "Text Only"),
            ("image_left", "Image Left"),
            ("image_right", "Image Right"),
            ("image_top", "Image Top"),
        ],
        default="image_right",
    )
    title = fields.Char()
    subtitle = fields.Char()
    body_content = fields.Html(sanitize_attributes=False)
    image = fields.Image(string="Image", max_width=1920, max_height=1080)
    image_alt = fields.Char(string="Image Alt Text")
    icon = fields.Char(
        string="Icon Class",
        help="Font Awesome icon class, e.g. fa-heartbeat",
    )
    button_text = fields.Char(string="Primary Button Text")
    button_url = fields.Char(string="Primary Button URL", default="/my/hospital")
    button_text_2 = fields.Char(string="Secondary Button Text")
    button_url_2 = fields.Char(string="Secondary Button URL")
    stat_value = fields.Char(string="Statistic Value", help="For statistics sections, e.g. 24/7")
    stat_label = fields.Char(string="Statistic Label")
    phone = fields.Char(string="Phone")
    email = fields.Char(string="Email")
    address = fields.Text(string="Address")
    working_hours = fields.Char(string="Working Hours")
    contact_url = fields.Char(string="Contact URL", default="/contactus")
    facebook_url = fields.Char(string="Facebook URL")
    twitter_url = fields.Char(string="Twitter URL")
    instagram_url = fields.Char(string="Instagram URL")
    linkedin_url = fields.Char(string="LinkedIn URL")
    copyright_text = fields.Char(
        string="Copyright Text",
        default="© Smart Hospital. All rights reserved.",
    )
    background_style = fields.Selection(
        [
            ("light", "Light"),
            ("white", "White"),
            ("primary", "Primary Gradient"),
            ("accent", "Accent"),
        ],
        default="white",
    )

    _LAYOUT_SECTION_TYPES = ("header", "footer")

    @api.model
    def get_published_contents(self, website=None):
        domain = [("is_published", "=", True), ("active", "=", True)]
        return self.sudo().search(domain, order="sequence, id")

    @api.model
    def get_published_body_contents(self):
        return self.get_published_contents().filtered(
            lambda content: content.section_type not in self._LAYOUT_SECTION_TYPES
        )

    @api.model
    def get_published_by_type(self, section_type):
        return self.sudo().search(
            [
                ("section_type", "=", section_type),
                ("is_published", "=", True),
                ("active", "=", True),
            ],
            order="sequence, id",
            limit=1,
        )

    @api.model
    def prepare_home_sections(self, contents):
        sections = []
        buffer = []
        buffer_type = None

        def flush():
            nonlocal buffer, buffer_type
            if buffer:
                sections.append({"kind": buffer_type, "items": buffer})
                buffer = []
                buffer_type = None

        for content in contents:
            if content.section_type in ("feature", "stats"):
                if buffer_type == content.section_type:
                    buffer.append(content)
                else:
                    flush()
                    buffer_type = content.section_type
                    buffer = [content]
            else:
                flush()
                sections.append({"kind": "single", "item": content})
        flush()
        return sections

    def action_publish(self):
        for rec in self:
            if rec.section_type in self._LAYOUT_SECTION_TYPES:
                self.search(
                    [
                        ("section_type", "=", rec.section_type),
                        ("id", "!=", rec.id),
                        ("is_published", "=", True),
                    ]
                ).write({"is_published": False})
            rec.write(
                {
                    "is_published": True,
                    "published_date": fields.Datetime.now(),
                    "published_by_id": self.env.user.id,
                }
            )

    def action_unpublish(self):
        self.write({"is_published": False})

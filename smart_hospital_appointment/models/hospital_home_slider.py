import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

YOUTUBE_RE = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})")
VIMEO_RE = re.compile(r"vimeo\.com/(?:.*/)?(\d+)")
VIDEO_MIMETYPES = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/mp4",
    "webm": "video/webm",
    "ogg": "video/ogg",
    "ogv": "video/ogg",
}


def _extension(name):
    name = (name or "").split("?", 1)[0].split("#", 1)[0]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


class HospitalHomeSlider(models.Model):
    _name = "hospital.home.slider"
    _description = "Website Home Slider"
    _order = "sequence, id"

    name = fields.Char(string="Internal Name", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    media_type = fields.Selection(
        [("image", "Image"), ("video", "Video")],
        default="image",
        required=True,
    )
    image = fields.Image(
        max_width=1920,
        max_height=1080,
        help="Wide landscape image, ideally 1920 × 800 px. "
        "For video slides it is shown while the video loads.",
    )
    video_source = fields.Selection(
        [("upload", "Upload File"), ("url", "Video Link")],
        default="upload",
    )
    video_file = fields.Binary(
        attachment=True,
        help="MP4 (H.264) or WebM file. Keep it short and compressed (ideally under 20 MB).",
    )
    video_filename = fields.Char()
    video_url = fields.Char(
        string="Video Link",
        help="YouTube or Vimeo link, or a direct link to an .mp4 / .webm file.",
    )
    video_kind = fields.Selection(
        [("file", "File"), ("youtube", "YouTube"), ("vimeo", "Vimeo")],
        compute="_compute_video_embed",
    )
    video_src = fields.Char(compute="_compute_video_embed")
    video_mimetype = fields.Char(compute="_compute_video_embed")
    title = fields.Char(help="Large heading shown on the slide.")
    subtitle = fields.Text(help="Supporting text shown under the heading.")
    badge = fields.Char(help="Small label above the heading, e.g. 'New branch open'.")
    button_text = fields.Char(string="Primary Button Text")
    button_url = fields.Char(string="Primary Button URL", default="/appointment/book")
    button_text_2 = fields.Char(string="Secondary Button Text")
    button_url_2 = fields.Char(string="Secondary Button URL", default="/doctors")
    caption_align = fields.Selection(
        [("start", "Left"), ("center", "Center"), ("end", "Right")],
        string="Caption Alignment",
        default="start",
        required=True,
    )

    @api.depends("media_type", "video_source", "video_url", "video_filename")
    def _compute_video_embed(self):
        for slide in self:
            kind = src = mimetype = False
            if slide.media_type == "video" and slide.video_source == "upload" and slide.id:
                kind = "file"
                src = f"/web/content/hospital.home.slider/{slide.id}/video_file"
                mimetype = VIDEO_MIMETYPES.get(_extension(slide.video_filename), "video/mp4")
            elif slide.media_type == "video" and slide.video_source == "url" and slide.video_url:
                url = slide.video_url.strip()
                youtube = YOUTUBE_RE.search(url)
                vimeo = VIMEO_RE.search(url)
                if youtube:
                    vid = youtube.group(1)
                    kind = "youtube"
                    src = (
                        f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&mute=1&loop=1"
                        f"&playlist={vid}&controls=0&rel=0&playsinline=1&modestbranding=1&disablekb=1"
                    )
                elif vimeo:
                    kind = "vimeo"
                    src = f"https://player.vimeo.com/video/{vimeo.group(1)}?background=1&autoplay=1&loop=1&muted=1"
                elif _extension(url) in VIDEO_MIMETYPES:
                    kind = "file"
                    src = url
                    mimetype = VIDEO_MIMETYPES[_extension(url)]
            slide.video_kind = kind
            slide.video_src = src
            slide.video_mimetype = mimetype

    @api.constrains("media_type", "image", "video_source", "video_file", "video_filename", "video_url")
    def _check_media(self):
        for slide in self:
            if slide.media_type == "image":
                if not slide.image:
                    raise ValidationError(_("Please upload an image for the slide '%s'.", slide.name))
                continue
            if slide.video_source == "upload":
                if not slide.video_file:
                    raise ValidationError(_("Please upload a video file for the slide '%s'.", slide.name))
                if slide.video_filename and _extension(slide.video_filename) not in VIDEO_MIMETYPES:
                    raise ValidationError(_("Unsupported video format. Please upload an MP4 or WebM file."))
            elif not slide.video_url:
                raise ValidationError(_("Please enter a video link for the slide '%s'.", slide.name))
            elif not slide.video_kind:
                raise ValidationError(_(
                    "Unsupported video link. Use a YouTube or Vimeo link, "
                    "or a direct link to an .mp4 / .webm file."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        slides = super().create(vals_list)
        slides._sync_video_mimetype()
        return slides

    def write(self, vals):
        res = super().write(vals)
        if "video_file" in vals or "video_filename" in vals:
            self._sync_video_mimetype()
        return res

    def _sync_video_mimetype(self):
        # Field attachments are named after the field, so Odoo cannot guess the type from an extension.
        attachments = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", self._name),
            ("res_field", "=", "video_file"),
            ("res_id", "in", self.ids),
        ])
        for attachment in attachments:
            slide = self.browse(attachment.res_id)
            mimetype = VIDEO_MIMETYPES.get(_extension(slide.video_filename), "video/mp4")
            if attachment.mimetype != mimetype:
                attachment.write({"mimetype": mimetype})

    @api.model
    def get_website_slides(self):
        return self.sudo().search([("active", "=", True)], order="sequence, id")

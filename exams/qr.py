import base64
import io

import qrcode
from qrcode.image.svg import SvgPathImage


def qr_data_uri(content: str) -> str:
    """Render ``content`` as an SVG QR code embedded in a data URI (allowed by the CSP img-src)."""
    buffer = io.BytesIO()
    qrcode.make(content, image_factory=SvgPathImage).save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()

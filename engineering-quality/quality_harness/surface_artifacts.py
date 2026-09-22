"""Independent pixel checks for unintended backing and decoration.

Callers provide a backdrop reference and design-owned allowance mask. Never
derive or expand the allowance from the image being evaluated. These checks
detect differences; attribution and intended-state pairing remain the caller's
responsibility.
"""

from dataclasses import dataclass

from PIL import Image, ImageChops


@dataclass(frozen=True)
class SurfaceArtifactResult:
    unexpected_pixels: int
    inspected_pixels: int
    bounds: tuple[int, int, int, int] | None

    @property
    def clean(self) -> bool:
        return self.unexpected_pixels == 0


def outside_allowed_surface(
    actual: Image.Image,
    backdrop: Image.Image,
    allowed: Image.Image,
    *,
    channel_tolerance: int = 3,
) -> SurfaceArtifactResult:
    """Compare outside explicit material/shadow/text/focus support regions."""
    if actual.size != backdrop.size or actual.size != allowed.size:
        raise ValueError("Capture, backdrop and allowance dimensions must agree")
    if not 0 <= channel_tolerance <= 255:
        raise ValueError("Invalid channel tolerance")
    delta = ImageChops.difference(actual.convert("RGB"), backdrop.convert("RGB"))
    red, green, blue = delta.split()
    magnitude = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed = magnitude.point(lambda value: 255 if value > channel_tolerance else 0)
    inspection = allowed.convert("L").point(lambda value: 0 if value else 255)
    unexpected = ImageChops.multiply(changed, inspection)
    return SurfaceArtifactResult(
        unexpected.histogram()[255], inspection.histogram()[255], unexpected.getbbox()
    )


def clipped_shadow_edges(raster: Image.Image, *, alpha_tolerance: int = 0) -> bool:
    """A finite decorative shadow must fall to transparent at its raster edge.

    Use only on raised-control shadow rasters whose contract requires a free
    perimeter. Flush panels, media crops and intentionally edge-to-edge surfaces
    are excluded. This does not evaluate whether the interior shadow is attractive.
    """
    if raster.mode != "RGBA":
        raise ValueError("Shadow inspection requires explicit RGBA pixels")
    alpha = raster.getchannel("A")
    width, height = raster.size
    edges = (
        (0, 0, width, 1),
        (0, height - 1, width, height),
        (0, 0, 1, height),
        (width - 1, 0, width, height),
    )
    return any(alpha.crop(edge).getextrema()[1] > alpha_tolerance for edge in edges)


def stale_decoration(
    restored: Image.Image,
    original: Image.Image,
    stable_region: Image.Image,
    *,
    channel_tolerance: int = 3,
) -> SurfaceArtifactResult:
    """Compare equal-content/equal-hover states before focus and after its exit.

    The caller supplies the stable region and must separately prove focus entered,
    the focus decoration was visible, and focus exited. Dynamic content is excluded
    explicitly. A changed hover/selection/theme is not a valid comparison pair.
    """
    ignored = ImageChops.invert(stable_region.convert("L"))
    return outside_allowed_surface(
        restored, original, ignored, channel_tolerance=channel_tolerance
    )

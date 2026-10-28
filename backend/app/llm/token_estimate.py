"""Input token estimate (no network): characters / 3.5 for text, plus a cost per page image.

Conservative on purpose: it gates extraction against MAX_INPUT_TOKENS before any call. The image
cost follows OpenAI's high-detail tile formula. Every constant lives here.
"""

import math
from collections.abc import Callable, Sequence

from app.llm.client import ImagePart, PromptPart

# Text: one token per this many characters (lower than usual English, so it over-estimates)
CHARACTERS_PER_TOKEN = 3.5

# Images (high detail): fit within the largest side, scale the short side down to the tile
# side length, then a fixed base cost plus a cost per 512-pixel tile
IMAGE_MAX_SIDE = 2048
IMAGE_SHORT_SIDE = 768
IMAGE_TILE_SIZE = 512
IMAGE_BASE_TOKENS = 85
IMAGE_TILE_TOKENS = 170

# Reads an image's (width, height) in pixels from its run store reference
ImageSizeReader = Callable[[str], tuple[int, int]]


def estimate_text_tokens(text: str) -> int:
    """Return the estimated tokens of a text, rounded up."""
    return math.ceil(len(text) / CHARACTERS_PER_TOKEN)


def estimate_image_tokens(width: int, height: int) -> int:
    """Return the high-detail token cost of an image of this size."""
    # Fit the image inside the largest allowed square, keeping its shape
    scale = min(1.0, IMAGE_MAX_SIDE / max(width, height))
    fitted_width, fitted_height = width * scale, height * scale
    # Then scale it so its short side is at most the short-side limit
    scale = min(1.0, IMAGE_SHORT_SIDE / min(fitted_width, fitted_height))
    final_width, final_height = fitted_width * scale, fitted_height * scale
    tiles = math.ceil(final_width / IMAGE_TILE_SIZE) * math.ceil(final_height / IMAGE_TILE_SIZE)
    return IMAGE_BASE_TOKENS + IMAGE_TILE_TOKENS * tiles


def estimate_parts_tokens(
    parts: Sequence[PromptPart], read_image_size: ImageSizeReader, schema_text: str = ""
) -> int:
    """Return the estimated input tokens of prompt parts plus the JSON schema text sent along."""
    total = estimate_text_tokens(schema_text)
    for part in parts:
        if isinstance(part, ImagePart):
            width, height = read_image_size(part.image_ref)
            total += estimate_image_tokens(width, height)
        else:
            total += estimate_text_tokens(part.text)
    return total

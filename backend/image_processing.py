"""Validate JPEG/PNG pixels and render a bounded original-image preview."""
import io
from PIL import Image, UnidentifiedImageError

MAX_PIXELS=20_000_000


def image_png(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as original:
            if original.format not in {'JPEG','PNG'}:raise ValueError('Choose a genuine JPEG or PNG image.')
            if original.width<1 or original.height<1 or original.width*original.height>MAX_PIXELS:
                raise ValueError('Image exceeds the 20 megapixel processing limit.')
            original.load()
            image=original.convert('RGBA')
            image.thumbnail((3200,3200))
            canvas=Image.new('RGB',image.size,'white');canvas.paste(image,mask=image.getchannel('A'))
            output=io.BytesIO();canvas.save(output,format='PNG')
            return output.getvalue()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:
        raise ValueError('The image is damaged or is not a supported JPEG/PNG file.') from error

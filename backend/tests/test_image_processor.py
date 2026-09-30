from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from app.domain.errors import AppError
from app.infrastructure.storage.image_inputs import assert_supported_image, save_id_photos, validate_id_photos
from app.infrastructure.storage.image_processor import ImageProcessingError, ImageProcessor
from app.infrastructure.storage.artifact_store import digest
from app.settings import Settings


def make_image(image_format: str, *, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", (40, 20), "red")
    buffer = BytesIO()
    options = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        options["exif"] = exif
    if image_format == "MPO":
        options.update(save_all=True, append_images=[Image.new("RGB", (40, 20), "blue")])
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


class ImageProcessorTests(unittest.TestCase):
    def test_standard_images_keep_original_bytes(self):
        for image_format, extension in [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")]:
            with self.subTest(image_format=image_format):
                data = make_image(image_format)
                result = ImageProcessor.prepare_upload(data)
                self.assertEqual(result.data, data)
                self.assertEqual(result.extension, extension)

    def test_mpo_main_image_orientation_and_storage(self):
        data = make_image("MPO", orientation=6)
        validated = validate_id_photos([("photo.jpeg", data)], 10)
        with TemporaryDirectory() as directory:
            settings = Settings(data_dir=Path(directory))
            stored = save_id_photos(settings, "test-pet", validated)[0]
            path = settings.data_dir / stored.path
            assert_supported_image(path)
            self.assertEqual(stored.input_hash, digest(path.read_bytes()))
            self.assertEqual(path.suffix, ".jpg")
            with Image.open(path) as image:
                image.load()
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (20, 40))
                self.assertIsNone(image.getexif().get(274))
                red, green, blue = image.getpixel((10, 10))
                self.assertGreater(red, 200)
                self.assertLess(blue, 30)

    def test_invalid_and_unsupported_images_are_rejected(self):
        for data in (b"not an image", make_image("GIF"), make_image("JPEG")[:100]):
            with self.subTest(data_size=len(data)):
                with self.assertRaises(ImageProcessingError):
                    ImageProcessor.prepare_upload(data)
        with self.assertRaises(AppError) as caught:
            validate_id_photos([("invalid.jpeg", b"invalid")], 10)
        self.assertEqual(caught.exception.code, "IMAGE_TYPE_UNSUPPORTED")

    def test_png_output_handles_cmyk_and_keeps_png(self):
        png = make_image("PNG")
        self.assertEqual(ImageProcessor.ensure_png(png), png)
        buffer = BytesIO()
        Image.new("CMYK", (10, 20)).save(buffer, format="JPEG")
        with Image.open(BytesIO(ImageProcessor.ensure_png(buffer.getvalue()))) as image:
            image.load()
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGB")

    def test_upload_size_limit(self):
        with self.assertRaises(AppError) as caught:
            validate_id_photos([("large.jpeg", b"x" * (1024 * 1024 + 1))], 1)
        self.assertEqual(caught.exception.code, "IMAGE_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()

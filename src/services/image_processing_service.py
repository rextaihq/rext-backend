"""
Image Processing Service

Handles image optimization, thumbnail generation, and metadata extraction.
Uses Pillow (PIL) for image manipulation.
"""

from PIL import Image, ImageOps, features, ExifTags
from io import BytesIO
from typing import Tuple, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ImageProcessingService:
    """
    Service for image processing operations.

    Features:
    - Image optimization (resize, compress)
    - Thumbnail generation (multiple sizes)
    - Metadata extraction (dimensions, format, mode)
    - Format conversion
    - EXIF orientation handling
    """

    def __init__(
        self,
        thumbnail_size: int = 300,
        max_width: int = 2000,
        max_height: int = 2000,
        quality: int = 85
    ):
        """
        Initialize image processing service.

        Args:
            thumbnail_size: Max dimension for thumbnails
            max_width: Max width for optimized images
            max_height: Max height for optimized images
            quality: JPEG quality (1-100)
        """
        self.thumbnail_size = thumbnail_size
        self.max_width = max_width
        self.max_height = max_height
        self.quality = quality

        # Predefined thumbnail sizes
        self.thumbnail_sizes = {
            'small': 150,
            'medium': 300,
            'large': 600
        }

        # Validate runtime image format support
        self.webp_supported = features.check_module("webp")
        if not self.webp_supported:
            logger.warning(
                "WEBP support is not available in this Pillow installation. "
                "WEBP images will not be processed. Install libwebp and "
                "reinstall Pillow to enable WEBP support."
            )
    
    def is_animated(self, file: BytesIO) -> bool:
        """
        Check if an image file contains animation (multiple frames).

        Args:
            file: Image file as BytesIO

        Returns:
            True if the image has more than one frame
        """
        try:
            with Image.open(file) as img:
                return getattr(img, 'is_animated', False)
        except Exception:
            return False
        finally:
            file.seek(0)

    def get_image_dimensions(self, file: BytesIO) -> Tuple[int, int]:
        """
        Get image width and height.

        Args:
            file: Image file as BytesIO

        Returns:
            Tuple of (width, height)
        """
        try:
            with Image.open(file) as img:
                img = ImageOps.exif_transpose(img)
                return img.size
        except Exception as e:
            logger.error(f"Error getting image dimensions: {e}")
            raise ValueError(f"Invalid image file: {e}")

    def optimize_image(
        self,
        file: BytesIO,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        quality: Optional[int] = None
    ) -> BytesIO:
        """
        Optimize image for web delivery.

        Operations:
        - Resize if larger than max dimensions
        - Convert RGBA to RGB for JPEG
        - Handle EXIF orientation
        - Compress with specified quality

        Args:
            file: Image file as BytesIO
            max_width: Maximum width (uses default if None)
            max_height: Maximum height (uses default if None)
            quality: JPEG quality (uses default if None)

        Returns:
            Optimized image as BytesIO
        """
        max_width = max_width or self.max_width
        max_height = max_height or self.max_height
        quality = quality or self.quality
        try:
            with Image.open(file) as img:
                # Check if animated — skip optimization to preserve all frames
                if getattr(img, 'is_animated', False):
                    logger.info(
                        f"Skipping optimization for animated image "
                        f"({getattr(img, 'n_frames', 1)} frames, format={img.format})"
                    )
                    file.seek(0)
                    return file

                # Handle EXIF orientation (rotate based on EXIF data)
                img = ImageOps.exif_transpose(img)

        try:
            with Image.open(file) as img:
                # Handle EXIF orientation (rotate based on EXIF data)
                img = ImageOps.exif_transpose(img)

                # Store original format
                original_format = img.format or 'JPEG'

                # Validate WEBP support if the image is WEBP
                if original_format == 'WEBP' and not self.webp_supported:
                    logger.warning("WEBP image received but WEBP support is not available")
                    raise ValueError(
                        "WEBP image processing is not available. "
                        "The server is missing libwebp support."
                    )

                # Convert RGBA to RGB if saving as JPEG
                if img.mode in ('RGBA', 'LA', 'P') and original_format in ('JPEG', 'JPG'):
                    # Create white background
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    # Paste with alpha channel as mask if available
                    if img.mode == 'RGBA':
                        rgb_img.paste(img, mask=img.split()[3])
                    else:
                        rgb_img.paste(img)
                    img = rgb_img
                elif img.mode not in ('RGB', 'L'):
                    # Convert other modes to RGB
                    img = img.convert('RGB')

                # Resize if image is too large
                if img.width > max_width or img.height > max_height:
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # Save optimized image
                output = BytesIO()
                save_format = original_format if original_format in ('JPEG', 'PNG', 'WEBP') else 'JPEG'

                if save_format in ('JPEG', 'JPG'):
                    img.save(output, format='JPEG', quality=quality, optimize=True)
                elif save_format == 'PNG':
                    img.save(output, format='PNG', optimize=True)
                elif save_format == 'WEBP':
                    img.save(output, format='WEBP', quality=quality, optimize=True)
                else:
                    img.save(output, format='JPEG', quality=quality, optimize=True)

                output.seek(0)
                return output

        except Exception as e:
            logger.error(f"Error optimizing image: {e}")
            raise ValueError(f"Failed to optimize image: {e}")

    def create_thumbnail(
        self,
        file: BytesIO,
        size: str = 'medium',
        custom_size: Optional[int] = None
    ) -> BytesIO:
        """
        Create thumbnail from image.

        Args:
            file: Image file as BytesIO
            size: Predefined size name ('small', 'medium', 'large')
            custom_size: Custom max dimension (overrides size parameter)

        Returns:
            Thumbnail image as BytesIO (JPEG format)
        """
        target_size = custom_size or self.thumbnail_sizes.get(size, self.thumbnail_size)
        try:
            with Image.open(file) as img:
                # For animated images, create a static thumbnail from the first frame
                # but log a warning that animation is not preserved in thumbnail
                if getattr(img, 'is_animated', False):
                    logger.info(
                        f"Creating static thumbnail from first frame of animated image "
                        f"({getattr(img, 'n_frames', 1)} frames)"
                    )
                    # Continue with normal thumbnail logic (first frame only is acceptable for thumbnails)

                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)

        try:
            with Image.open(file) as img:
                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)

                # Convert to RGB if needed (for JPEG)
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        rgb_img.paste(img, mask=img.split()[3])
                    else:
                        rgb_img.paste(img)
                    img = rgb_img
                elif img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                # Create thumbnail (maintains aspect ratio)
                img.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)

                # Save as JPEG
                output = BytesIO()
                img.save(output, format='JPEG', quality=self.quality, optimize=True)
                output.seek(0)
                return output

        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            raise ValueError(f"Failed to create thumbnail: {e}")

    def extract_metadata(self, file: BytesIO) -> Dict[str, Any]:
        """
        Extract image metadata.

        Args:
            file: Image file as BytesIO

        Returns:
            Dictionary with metadata:
            - format: Image format (JPEG, PNG, etc.)
            - mode: Color mode (RGB, RGBA, etc.)
            - width: Image width
            - height: Image height
            - has_transparency: Whether image has alpha channel
            - file_size: Approximate file size in bytes
        """
        try:
            with Image.open(file) as img:
                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)

                # Get file size
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()
                file.seek(0)  # Reset to beginning
                
                metadata = {
                    'format': img.format,
                    'mode': img.mode,
                    'width': img.width,
                    'height': img.height,
                    'has_transparency': img.mode in ('RGBA', 'LA', 'P'),
                    'file_size': file_size,
                    'is_animated': getattr(img, 'is_animated', False),
                    'frame_count': getattr(img, 'n_frames', 1),
                }

                # Add EXIF data if available (using public getexif() API)
                exif_data = img.getexif()
                if exif_data:
                    try:
                        metadata['has_exif'] = True
                        # Access IFD0 tags using named constants
                        make = exif_data.get(ExifTags.Base.Make)
                        if make:
                            metadata['camera_make'] = str(make).strip()
                        model = exif_data.get(ExifTags.Base.Model)
                        if model:
                            metadata['camera_model'] = str(model).strip()
                        datetime_tag = exif_data.get(ExifTags.Base.DateTime)
                        if datetime_tag:
                            metadata['datetime'] = str(datetime_tag)

                        # Access EXIF IFD for additional tags if needed
                        exif_ifd = exif_data.get_ifd(ExifTags.IFD.Exif)
                        if exif_ifd:
                            # ExposureTime, FNumber, ISO, etc. could be extracted here
                            metadata['has_exif_ifd'] = True
                    except Exception:
                        # EXIF parsing is best-effort — don't fail the upload
                        pass

                return metadata

        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            raise ValueError(f"Failed to extract metadata: {e}")

    def validate_image(
        self,
        file: BytesIO,
        max_size_mb: Optional[float] = None,
        allowed_formats: Optional[list] = None
    ) -> Tuple[bool, str]:
        """
        Validate image file.

        Args:
            file: Image file as BytesIO
            max_size_mb: Maximum file size in MB
            allowed_formats: List of allowed formats (e.g., ['JPEG', 'PNG'])

        Returns:
            Tuple of (is_valid, error_message)
            error_message is empty string if valid
        """
        try:
            # Check file size
            if max_size_mb:
                file.seek(0, 2)
                file_size_mb = file.tell() / (1024 * 1024)
                file.seek(0)
                if file_size_mb > max_size_mb:
                    return False, f"File size ({file_size_mb:.2f}MB) exceeds maximum ({max_size_mb}MB)"

            # Try to open image
            with Image.open(file) as img:
                # Check format
                if allowed_formats and img.format not in allowed_formats:
                    return False, f"Format {img.format} not allowed. Allowed: {', '.join(allowed_formats)}"

                # Verify image is not corrupted
                img.verify()

            file.seek(0)  # Reset file pointer
            return True, ""

        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return False, f"Invalid image file: {str(e)}"

    def convert_format(
        self,
        file: BytesIO,
        target_format: str = 'JPEG',
        quality: Optional[int] = None
    ) -> BytesIO:
        """
        Convert image to different format.

        Args:
            file: Image file as BytesIO
            target_format: Target format (JPEG, PNG, WEBP)
            quality: Quality for lossy formats (uses default if None)

        Returns:
            Converted image as BytesIO
        """
        quality = quality or self.quality

        with Image.open(file) as img:
                # Validate WEBP support for target format
                if target_format.upper() == 'WEBP' and not self.webp_supported:
                    raise ValueError(
                        "Cannot convert to WEBP: WEBP support is not available. "
                        "Install libwebp and reinstall Pillow."
                    )

                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)

        try:
            with Image.open(file) as img:
                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)

                # Convert mode based on target format
                if target_format.upper() in ('JPEG', 'JPG'):
                    if img.mode in ('RGBA', 'LA', 'P'):
                        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'RGBA':
                            rgb_img.paste(img, mask=img.split()[3])
                        else:
                            rgb_img.paste(img)
                        img = rgb_img
                    elif img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')

                # Save in target format
                output = BytesIO()

                if target_format.upper() in ('JPEG', 'JPG'):
                    img.save(output, format='JPEG', quality=quality, optimize=True)
                elif target_format.upper() == 'PNG':
                    img.save(output, format='PNG', optimize=True)
                elif target_format.upper() == 'WEBP':
                    img.save(output, format='WEBP', quality=quality, optimize=True)
                else:
                    raise ValueError(f"Unsupported target format: {target_format}")

                output.seek(0)
                return output

        except Exception as e:
            logger.error(f"Error converting image format: {e}")
            raise ValueError(f"Failed to convert image: {e}")

    def get_supported_formats(self) -> dict:
        """
        Return a dictionary of supported image format capabilities.
        Useful for health checks and configuration validation.

        Returns:
            Dict with format names and their support status
        """
        return {
            "jpeg": True,  # Always supported by Pillow core
            "png": True,   # Always supported by Pillow core
            "gif": True,   # Always supported by Pillow core
            "webp": self.webp_supported,
            "webp_version": features.version_module("webp") if self.webp_supported else None,
        }
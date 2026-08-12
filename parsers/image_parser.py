"""
parsers/image_parser.py — Image parsing via Ollama Vision-Language Model with Tesseract fallback.

Public API
----------
extract_text(filepath) -> str
    Extracts text & content description from an image using local VLM (Ollama).
    Falls back to Tesseract OCR if Ollama VLM fails/times out.
    On any error returns "" — never raises.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import tempfile
from pathlib import Path

import config

log = logging.getLogger(__name__)

# Minimum width in pixels before upscaling for Tesseract fallback.
MIN_WIDTH_PX = 1_000

# Maximum dimension in pixels (width or height) for VLM processing to optimize memory and speed.
MAX_VLM_DIM_PX = 800

VISION_PROMPT = "Describe what this image shows in detail, and transcribe any visible text in the image."


def extract_text_tesseract_fallback(filepath: str) -> str:
    """
    Run Tesseract OCR on an image file and return extracted text.
    Fallback method when Ollama VLM is unavailable or fails.
    """
    try:
        import pytesseract
        from PIL import Image, ImageEnhance
    except ImportError:
        log.error(
            "pytesseract or Pillow is not installed. "
            "Run: pip install pytesseract pillow"
        )
        return ""

    try:
        img = Image.open(filepath)
    except Exception as exc:
        log.warning("Cannot open image '%s' (corrupted or unsupported format): %s", filepath, exc)
        return ""

    try:
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.0)
        w, h = img.size
        if w < MIN_WIDTH_PX:
            scale = MIN_WIDTH_PX / w
            img = img.resize(
                (int(w * scale), int(h * scale)),
                resample=Image.Resampling.LANCZOS,
            )
        text: str = pytesseract.image_to_string(img, lang="eng")
        return text.strip()
    except pytesseract.TesseractNotFoundError:
        log.error(
            "Tesseract executable not found. "
            "Install Tesseract and ensure it is on your PATH."
        )
        return ""
    except Exception as exc:
        log.warning("OCR failed for '%s': %s", filepath, exc)
        return ""


def _downscale_if_large(filepath: str) -> str:
    """
    Downscale image if longest side > MAX_VLM_DIM_PX to optimize vision model speed/memory.
    Returns path to use (original or temporary downscaled file).
    """
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            w, h = img.size
            if max(w, h) <= MAX_VLM_DIM_PX:
                return filepath

            scale = MAX_VLM_DIM_PX / float(max(w, h))
            new_size = (int(w * scale), int(h * scale))
            resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Save downscaled copy in system temp
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp_path = tmp.name
            tmp.close()
            
            if resized_img.mode != "RGB":
                resized_img = resized_img.convert("RGB")
            resized_img.save(tmp_path, format="JPEG", quality=85)
            return tmp_path
    except Exception as exc:
        log.debug("Image downscaling skipped for '%s': %s", filepath, exc)
        return filepath


def _call_ollama_vision(filepath: str) -> tuple[str, str]:
    """
    Perform Ollama VLM call to extract text and description from an image.
    Returns tuple of (extracted_text, description).
    """
    import ollama

    path_obj = Path(filepath).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"Image path does not exist: {filepath}")

    target_path = _downscale_if_large(str(path_obj))

    try:
        response = ollama.chat(
            model=config.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": VISION_PROMPT,
                    "images": [target_path],
                }
            ],
        )

        content = response["message"]["content"].strip()

        # Match exact header lines: "TEXT:" and "DESCRIPTION:" at line starts
        text_match = re.search(r"^\s*TEXT:\s*(.*?)(?=^\s*DESCRIPTION:|$)", content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
        desc_match = re.search(r"^\s*DESCRIPTION:\s*(.*)", content, re.DOTALL | re.MULTILINE | re.IGNORECASE)

        extracted_text = text_match.group(1).strip() if text_match else ""
        description = desc_match.group(1).strip() if desc_match else ""

        # Fallback: if explicit header tags were not used by model, treat whole response as description
        if not text_match and not desc_match:
            description = content.strip()
        elif desc_match and not description:
            description = content.strip()

        log.info("VLM Output Parsed — extracted_text len=%d, description len=%d", len(extracted_text), len(description))
        return extracted_text, description

    finally:
        if target_path != str(path_obj) and Path(target_path).exists():
            try:
                Path(target_path).unlink(missing_ok=True)
            except Exception:
                pass


def extract_text(filepath: str) -> str:
    """
    Fast-path image text extraction:
    1. Try Tesseract OCR first for instant sub-second text extraction.
    2. Fall back to fast Ollama VLM (max 3s timeout) if OCR is empty.
    """
    try:
        # Fast-path 1: Tesseract OCR (0.05s per image)
        ocr_text = extract_text_tesseract_fallback(filepath)
        if ocr_text and len(ocr_text.strip()) > 5:
            return ocr_text

        # Fast-path 2: Short 3s timeout for Ollama VLM
        timeout = getattr(config, "VISION_TIMEOUT_SECONDS", 3)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call_ollama_vision, filepath)
                extracted_text, description = future.result(timeout=timeout)

            has_text = bool(extracted_text and extracted_text.lower().strip() != "none")
            if has_text and description:
                return f"{description}\n\n{extracted_text}"
            elif description:
                return description
            elif has_text:
                return extracted_text

            return ocr_text or ""
        except (concurrent.futures.TimeoutError, Exception) as exc:
            log.debug("Ollama Vision skipped/timed out for '%s' (%s)", filepath, exc)
            return ocr_text or ""

    except Exception as exc:
        log.warning("Unhandled exception in image_parser for '%s': %s", filepath, exc)
        return ""

    except Exception as exc:
        log.warning("Unhandled exception in image_parser for '%s': %s", filepath, exc)
        return ""

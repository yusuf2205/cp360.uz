"""Turn uploaded bytes into text blocks with source references. Content is untrusted."""
import io
import zipfile
from dataclasses import dataclass, field

from ...config import settings


class UnsupportedFile(Exception):
    pass


class EngineUnavailable(Exception):
    """OCR / speech-to-text engine is not configured. Surfaced to the user, never faked."""


@dataclass
class Block:
    text: str
    ref: dict  # {"page": 1} | {"sheet": "X", "row": 5} | {"line": 3}
    cells: list[str] | None = None  # table row cells, when the source is tabular


@dataclass
class Parsed:
    kind: str
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


def sniff(data: bytes, filename: str = "") -> str:
    """Detect by content, not by extension. Raises UnsupportedFile for anything else (incl. executables)."""
    h = data[:16]
    if h[:2] == b"MZ" or h[:4] == b"\x7fELF" or h[:2] == b"#!" or data[:5].lower() == b"<?php":
        raise UnsupportedFile("исполняемые файлы и скрипты не принимаются")
    if h[:5] == b"%PDF-":
        return "pdf"
    if h[:8] == b"\x89PNG\r\n\x1a\n" or h[:3] == b"\xff\xd8\xff" or h[:6] in (b"GIF87a", b"GIF89a") or (h[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return "image"
    if h[:4] == b"PK\x03\x04":
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            raise UnsupportedFile("файл повреждён")
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        raise UnsupportedFile("этот тип архива не поддерживается")
    if h[:3] == b"ID3" or h[:4] in (b"OggS", b"fLaC") or (h[:4] == b"RIFF" and data[8:12] == b"WAVE") or data[4:8] == b"ftyp" or h[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio"
    if b"\x00" not in data[:4096]:
        try:
            data[:65536].decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            try:
                data[:65536].decode("cp1251")
                return "text"
            except UnicodeDecodeError:
                pass
    raise UnsupportedFile("тип файла не распознан. Подходят: PDF, фото, Excel, Word, текст, аудио")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_text(data: bytes) -> Parsed:
    p = Parsed("text")
    for i, line in enumerate(_decode(data).splitlines(), 1):
        if line.strip():
            p.blocks.append(Block(line.strip(), {"line": i}))
    return p


def parse_xlsx(data: bytes) -> Parsed:
    from openpyxl import load_workbook

    p = Parsed("xlsx")
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    for ws in wb.worksheets:
        for r, row in enumerate(ws.iter_rows(values_only=True), 1):
            cells = ["" if v is None else str(v).strip() for v in row]
            if any(cells):
                p.blocks.append(Block(" | ".join(c for c in cells if c), {"sheet": ws.title, "row": r}, cells))
    return p


def parse_docx(data: bytes) -> Parsed:
    import docx

    p = Parsed("docx")
    d = docx.Document(io.BytesIO(data))
    for i, para in enumerate(d.paragraphs, 1):
        if para.text.strip():
            p.blocks.append(Block(para.text.strip(), {"paragraph": i}))
    for ti, t in enumerate(d.tables, 1):
        for ri, row in enumerate(t.rows, 1):
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                p.blocks.append(Block(" | ".join(c for c in cells if c), {"table": ti, "row": ri}, cells))
    return p


def _ocr_image(img) -> str:
    """OCR with phone-photo hygiene: EXIF rotation, grey + contrast, upscale small images, and the page-segmentation
    mode that yields the most readable table rows (tried: block, column, auto)."""
    import pytesseract
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(img)
    img = ImageOps.autocontrast(img.convert("L"))
    if img.width < 1600:
        k = 1600 / img.width
        img = img.resize((1600, int(img.height * k)), Image.LANCZOS)
    from .engine import parse_text_row  # local import: engine imports this module

    best, best_hits = "", -1
    for cfg in ("--psm 6", "--psm 4", "--psm 3"):
        text = pytesseract.image_to_string(img, lang=settings.ocr_langs, config=cfg)
        hits = sum(1 for ln in text.splitlines() if parse_text_row(ln))
        if hits > best_hits or (hits == best_hits and len(text) > len(best)):
            best, best_hits = text, hits
        if best_hits >= 3 and cfg == "--psm 6":
            break  # good enough, do not spend more CPU
    return best


def parse_pdf(data: bytes) -> Parsed:
    from pypdf import PdfReader

    p = Parsed("pdf")
    scanned_pages: list[int] = []
    for pn, page in enumerate(PdfReader(io.BytesIO(data)).pages, 1):
        txt = (page.extract_text() or "").strip()
        if len(txt) < 20:
            scanned_pages.append(pn)
            continue
        for line in txt.splitlines():
            if line.strip():
                p.blocks.append(Block(line.strip(), {"page": pn}))
    if scanned_pages:  # image-only pages: render and OCR them
        try:
            import fitz  # PyMuPDF
            from PIL import Image
        except ImportError as e:
            if not p.blocks:
                raise EngineUnavailable("Это скан PDF, а компоненты распознавания (OCR) не установлены. Вставьте текст или введите цены вручную") from e
            p.warnings.append("some_pages_are_scans_and_were_skipped")
            return p
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            for pn in scanned_pages[:30]:
                pix = doc[pn - 1].get_pixmap(dpi=220)
                text = _ocr_image(Image.open(io.BytesIO(pix.tobytes("png"))))
                for i, line in enumerate(text.splitlines(), 1):
                    if line.strip():
                        p.blocks.append(Block(line.strip(), {"page": pn, "line": i}))
            p.warnings.append("ocr_text_may_contain_errors")
        except Exception as e:
            raise EngineUnavailable(f"Не удалось распознать (OCR) скан PDF: {e}") from e
    if not p.blocks:
        raise EngineUnavailable("В PDF не найден читаемый текст")
    return p


def parse_image(data: bytes) -> Parsed:
    try:
        from PIL import Image

        text = _ocr_image(Image.open(io.BytesIO(data)))
    except ImportError as e:
        raise EngineUnavailable("Распознавание текста с фото (OCR) не установлено на сервере. Вставьте текст или введите цены вручную") from e
    except Exception as e:  # tesseract binary missing, bad image, etc.
        raise EngineUnavailable(f"Не удалось распознать (OCR) изображение: {e}") from e
    p = Parsed("image", warnings=["ocr_text_may_contain_errors"])
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip():
            p.blocks.append(Block(line.strip(), {"line": i}))
    if not p.blocks:
        raise EngineUnavailable("На изображении не найден текст. Сделайте фото чётче, ровнее и при хорошем свете")
    return p


def parse_audio(data: bytes, filename: str) -> Parsed:
    if not settings.stt_url:
        raise EngineUnavailable("Распознавание голоса пока не подключено. Пришлите текст или фото либо введите цены вручную (администратору: задайте STT_URL)")
    import httpx

    r = httpx.post(settings.stt_url, files={"file": (filename or "audio", data)}, data={"model": "whisper-1"}, timeout=300)
    r.raise_for_status()
    p = Parsed("audio", warnings=["transcript_may_contain_errors"])
    for i, line in enumerate(r.json().get("text", "").splitlines(), 1):
        if line.strip():
            p.blocks.append(Block(line.strip(), {"line": i}))
    return p


def parse(data: bytes, filename: str = "") -> Parsed:
    kind = sniff(data, filename)
    return {
        "text": lambda: parse_text(data),
        "xlsx": lambda: parse_xlsx(data),
        "docx": lambda: parse_docx(data),
        "pdf": lambda: parse_pdf(data),
        "image": lambda: parse_image(data),
        "audio": lambda: parse_audio(data, filename),
    }[kind]()

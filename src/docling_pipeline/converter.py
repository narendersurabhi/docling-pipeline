"""Build a Docling DocumentConverter from pipeline configuration."""

from __future__ import annotations

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

from docling_pipeline.config import ConversionConfig


def build_pdf_options(cfg: ConversionConfig) -> PdfPipelineOptions:
    opts = PdfPipelineOptions()
    opts.do_ocr = cfg.do_ocr
    opts.do_table_structure = cfg.do_table_structure
    opts.table_structure_options.mode = TableFormerMode(cfg.table_mode)
    opts.generate_picture_images = cfg.generate_picture_images
    opts.images_scale = cfg.images_scale
    opts.accelerator_options = AcceleratorOptions(num_threads=cfg.num_threads, device=cfg.device)
    if cfg.document_timeout is not None:
        opts.document_timeout = cfg.document_timeout
    return opts


def build_converter(cfg: ConversionConfig) -> DocumentConverter:
    """PDFs and images go through the layout/OCR/table models; other formats use Docling's
    default (model-free) backends."""
    pdf_options = build_pdf_options(cfg)
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pdf_options),
        }
    )

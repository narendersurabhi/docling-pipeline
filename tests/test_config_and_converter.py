from pathlib import Path

import pytest
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import TableFormerMode
from pydantic import ValidationError

from docling_pipeline.config import ChunkerType, ConversionConfig, ExportFormat, PipelineConfig
from docling_pipeline.converter import build_converter, build_pdf_options

REPO_CONFIG = Path(__file__).parent.parent / "configs" / "pipeline.yaml"


@pytest.mark.spec("FR-009")
def test_example_config_loads():
    cfg = PipelineConfig.from_yaml(REPO_CONFIG)
    assert cfg.exports == [ExportFormat.MARKDOWN, ExportFormat.JSON]
    assert cfg.chunking.chunker is ChunkerType.HYBRID


@pytest.mark.spec("FR-009")
def test_missing_keys_take_defaults(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("output_dir: out\n")
    cfg = PipelineConfig.from_yaml(p)
    assert cfg.output_dir == Path("out")
    assert cfg.conversion.do_ocr is True
    assert cfg.chunking.max_tokens == 512


@pytest.mark.spec("FR-009")
@pytest.mark.parametrize(
    "yaml_text",
    [
        "exports: [pdf]",
        "conversion: {table_mode: slow}",
        "conversion: {device: tpu}",
        "chunking: {chunker: semantic}",
    ],
)
def test_invalid_values_are_rejected(tmp_path: Path, yaml_text: str):
    p = tmp_path / "c.yaml"
    p.write_text(yaml_text)
    with pytest.raises(ValidationError):
        PipelineConfig.from_yaml(p)


@pytest.mark.spec("FR-003")
def test_conversion_config_maps_to_docling_pdf_options():
    cfg = ConversionConfig(
        do_ocr=False,
        do_table_structure=False,
        table_mode="fast",
        generate_picture_images=True,
        images_scale=1.5,
        num_threads=2,
        device="cpu",
        document_timeout=30,
    )
    opts = build_pdf_options(cfg)
    assert opts.do_ocr is False
    assert opts.do_table_structure is False
    assert opts.table_structure_options.mode is TableFormerMode.FAST
    assert opts.generate_picture_images is True
    assert opts.images_scale == 1.5
    assert opts.accelerator_options.num_threads == 2
    assert opts.accelerator_options.device == "cpu"
    assert opts.document_timeout == 30


@pytest.mark.spec("FR-003")
def test_converter_routes_pdf_and_images_through_configured_pipeline():
    cfg = ConversionConfig(do_ocr=False)
    converter = build_converter(cfg)
    for fmt in (InputFormat.PDF, InputFormat.IMAGE):
        assert converter.format_to_options[fmt].pipeline_options.do_ocr is False

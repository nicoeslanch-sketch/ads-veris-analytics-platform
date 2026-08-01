from pathlib import Path

import pandas as pd

from app.config import Settings
from app.consolidation.generic_pipeline import run_general_pipeline
from app.consolidation.models import ConsolidationStatus, SourceRole
from app.consolidation.resources import ResourceMonitor
from app.consolidation.repository import MemoryConsolidationRepository
from app.consolidation.worker import ConsolidationWorker


def _csv(path: Path, frame: pd.DataFrame, separator: str = ",") -> Path:
    frame.to_csv(path, index=False, sep=separator, encoding="utf-8-sig")
    return path


def _run(sources, configs):
    settings = Settings(
        consolidation_memory_soft_limit_mb=3000,
        consolidation_memory_hard_limit_mb=3600,
        consolidation_temp_disk_min_mb=1,
    )
    monitor = ResourceMonitor(settings)
    try:
        return run_general_pipeline(sources, source_configs=configs, settings=settings, monitor=monitor)
    finally:
        monitor.stop()


def test_general_pipeline_preserves_primary_rows_and_detects_csv_separator(tmp_path):
    primary = _csv(tmp_path / "ventas.csv", pd.DataFrame({
        "Venta": [1, 2, 3], "SKU": ["A", "A", "B"], "Monto": [100, 200, 150],
    }), separator=",")
    products = _csv(tmp_path / "productos.csv", pd.DataFrame({
        "Codigo": ["A", "B"], "Producto": ["Azúcar", "Harina"], "Costo": [60, 90],
    }), separator=";")
    output = _run(
        {SourceRole.PRIMARY: primary, SourceRole.SUPPLEMENT_1: products},
        {
            SourceRole.PRIMARY: {"primary_key": "SKU"},
            SourceRole.SUPPLEMENT_1: {
                "label": "Productos", "primary_key": "SKU", "source_key": "Codigo",
            },
        },
    )
    assert len(output.annual) == 3
    assert output.annual["Producto"].tolist() == ["Azúcar", "Azúcar", "Harina"]
    assert output.annual["Costo"].tolist() == ["60", "60", "90"]
    assert output.manifest.row_counts["primary"] == 3


def test_duplicate_dimension_keys_are_excluded_without_multiplying_rows(tmp_path):
    primary = _csv(tmp_path / "principal.csv", pd.DataFrame({"ID": [1, 2], "Codigo": ["A", "B"]}))
    duplicate = _csv(tmp_path / "maestro.csv", pd.DataFrame({
        "Codigo": ["A", "A", "B"], "Nombre": ["Uno", "Otro", "Dos"],
    }))
    output = _run(
        {SourceRole.PRIMARY: primary, SourceRole.SUPPLEMENT_1: duplicate},
        {
            SourceRole.PRIMARY: {"primary_key": "Codigo"},
            SourceRole.SUPPLEMENT_1: {"primary_key": "Codigo", "source_key": "Codigo", "label": "Maestro"},
        },
    )
    assert len(output.annual) == 2
    assert pd.isna(output.annual.loc[0, "Nombre"])
    assert output.annual.loc[1, "Nombre"] == "Dos"
    assert output.manifest.status is ConsolidationStatus.VALID_WITH_WARNINGS
    assert any(issue.code == "supplement_1_duplicate_keys" for issue in output.manifest.issues)


def test_equivalence_adds_new_column_and_keeps_original(tmp_path):
    primary = _csv(tmp_path / "clientes.csv", pd.DataFrame({"Cliente": [1, 2], "Estado": ["A", "I"]}))
    book = _csv(tmp_path / "estados.csv", pd.DataFrame({"Codigo": ["A", "I"], "Texto": ["Activo", "Inactivo"]}))
    output = _run(
        {SourceRole.PRIMARY: primary, SourceRole.EQUIVALENCE_1: book},
        {
            SourceRole.PRIMARY: {"primary_key": "Cliente"},
            SourceRole.EQUIVALENCE_1: {
                "target_column": "Estado", "source_key": "Codigo", "value_column": "Texto",
                "output_column": "Estado_descripcion", "label": "Estados",
            },
        },
    )
    assert output.annual["Estado"].tolist() == ["A", "I"]
    assert output.annual["Estado_descripcion"].tolist() == ["Activo", "Inactivo"]
    assert output.manifest.status is ConsolidationStatus.CERTIFIED


def test_complete_generic_scenario_with_two_dimensions_and_equivalence(tmp_path):
    sales = _csv(tmp_path / "ventas.csv", pd.DataFrame({
        "ID_VENTA": [1, 2, 3, 4], "ID_PRODUCTO": ["A", "A", "B", "C"],
        "ID_CLIENTE": [10, 20, 10, 30], "COD_ESTADO": ["1", "2", "1", "9"],
        "MONTO": [100, 200, 150, 90],
    }))
    products = _csv(tmp_path / "productos.csv", pd.DataFrame({
        "ID_PRODUCTO": ["A", "A", "B", "C"],
        "PRODUCTO": ["Uno", "Uno conflictivo", "Dos", "Tres"],
        "COSTO": [60, 65, 90, 50],
    }))
    clients = _csv(tmp_path / "clientes.csv", pd.DataFrame({
        "ID_CLIENTE": [10, 20, 30], "SEGMENTO": ["PyME", "Empresa", "PyME"],
        "REGION": ["Norte", "Centro", "Sur"],
    }))
    states = _csv(tmp_path / "estados.csv", pd.DataFrame({
        "CODIGO": ["1", "2"], "DESCRIPCION": ["Pagada", "Pendiente"],
    }))
    output = _run(
        {
            SourceRole.PRIMARY: sales, SourceRole.SUPPLEMENT_1: products,
            SourceRole.SUPPLEMENT_2: clients, SourceRole.EQUIVALENCE_1: states,
        },
        {
            SourceRole.PRIMARY: {"primary_key": "ID_VENTA"},
            SourceRole.SUPPLEMENT_1: {"label": "Productos", "primary_key": "ID_PRODUCTO", "source_key": "ID_PRODUCTO"},
            SourceRole.SUPPLEMENT_2: {"label": "Clientes", "primary_key": "ID_CLIENTE", "source_key": "ID_CLIENTE"},
            SourceRole.EQUIVALENCE_1: {
                "label": "Estados", "target_column": "COD_ESTADO", "source_key": "CODIGO",
                "value_column": "DESCRIPCION", "output_column": "ESTADO_DESCRIPCION",
            },
        },
    )
    assert len(output.annual) == 4
    assert len(output.annual.columns) == 10
    assert output.manifest.status is ConsolidationStatus.VALID_WITH_WARNINGS
    assert output.annual.loc[0, "PRODUCTO"] is pd.NA or pd.isna(output.annual.loc[0, "PRODUCTO"])
    assert output.annual.loc[2, "PRODUCTO"] == "Dos"
    assert output.annual["SEGMENTO"].tolist() == ["PyME", "Empresa", "PyME", "PyME"]
    assert output.annual["ESTADO_DESCRIPCION"].tolist()[:3] == ["Pagada", "Pendiente", "Pagada"]
    assert pd.isna(output.annual.loc[3, "ESTADO_DESCRIPCION"])
    assert any(issue.code == "supplement_1_duplicate_keys" and issue.count == 1 for issue in output.manifest.issues)
    assert any(issue.code == "equivalence_1_unmapped" and issue.count == 1 for issue in output.manifest.issues)


def test_worker_routes_general_project_and_writes_generic_artifacts(tmp_path):
    primary = _csv(tmp_path / "ventas.csv", pd.DataFrame({"Venta": [1, 2], "SKU": ["A", "B"]}))
    repository = MemoryConsolidationRepository()
    project = repository.create_project("user", {
        "name": "Ventas", "config": {"template": "general", "include_historical_output": False},
        "config_hash": "a" * 64, "engine_version": "test",
    })
    repository.replace_sources(project["id"], "user", [{
        "role": SourceRole.PRIMARY.value,
        "dataset_id": "00000000-0000-0000-0000-000000000001",
        "local_path": str(primary),
        "selected_sheet": "Datos",
        "profile": {"configuration": {"primary_key": "SKU", "selected_sheet": "Datos"}},
    }])
    run = repository.enqueue_run(repository.get_project(project["id"], "user"), "b" * 64)
    settings = Settings(consolidation_temp_disk_min_mb=1)
    worker = ConsolidationWorker(repository, settings, output_root=tmp_path / "outputs")
    assert worker.run_once() is True
    completed = repository.get_run(run["id"], "user")
    assert completed["status"] == "certified"
    annual = next(item for item in completed["artifacts"] if item["kind"] == "annual")
    assert Path(annual["storage_path"]).name == "BASE_CONSOLIDADA.xlsx"

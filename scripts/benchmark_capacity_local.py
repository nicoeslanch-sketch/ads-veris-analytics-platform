"""Bounded synthetic benchmark. No uploads, network requests or credentials."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, nargs="+", default=[5000, 20000])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(rows < 100 or rows > 50000 for rows in args.rows):
        parser.error("This bounded local probe accepts 100 to 50,000 synthetic rows.")

    # Disable all optional outbound integrations before any Settings is loaded.
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "ANALYSIS_REDIS_URL", "ANTHROPIC_API_KEY"):
        os.environ[name] = ""
    os.environ["APP_ENV"] = "development"
    os.environ["DEV_AUTH_BYPASS"] = "false"
    from app.engine.loader import load_dataframe_with_report
    from app.routes import pipeline
    import psutil

    process = psutil.Process()
    sample_stop = threading.Event()
    peaks = []

    def sample_memory():
        while not sample_stop.wait(0.02):
            peaks.append(process.memory_info().rss)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    result = {
        "scope": "local synthetic CPU/RAM only; not a production load test or SLA",
        "python": platform.python_version(),
        "system": platform.system(),
        "logical_cpus": os.cpu_count(),
        "machine_ram_mb": round(psutil.virtual_memory().total / 1024**2),
        "baseline_rss_mb": round(process.memory_info().rss / 1024**2, 2),
        "workloads": [],
    }
    try:
        for rows in args.rows:
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["ID Venta", "Fecha", "Cliente", "Producto", "Categoria", "Sucursal", "Vendedor", "Canal", "Cantidad", "Precio Unitario", "Monto Venta", "Estado"])
            expected_total = 0
            for i in range(rows):
                amount = (i % 9 + 1) * (1000 + i % 997)
                expected_total += amount
                writer.writerow([f"V{i:08}", f"2025-{i % 12 + 1:02}-{i % 28 + 1:02}", f"C{i % 800:04}", f"P{i % 300:04}", f"Categoria {i % 7}", f"SUC{i % 5}", f"Vendedor {i % 20}", "Web" if i % 2 else "Local", i % 9 + 1, 1000 + i % 997, amount, "Vigente"])
            content = output.getvalue().encode("utf-8")
            filename = f"synthetic_{rows}.csv"
            record = {"rows": rows, "columns": 12, "csv_bytes": len(content)}
            before = process.memory_info().rss
            start_index = len(peaks)
            start = time.perf_counter()
            frame, report = load_dataframe_with_report(filename, content)
            record["load_seconds"] = round(time.perf_counter() - start, 4)
            start = time.perf_counter()
            pipeline._standardize_sync(filename, content, preloaded=(frame, report))
            record["standardize_seconds"] = round(time.perf_counter() - start, 4)
            start = time.perf_counter()
            cleaned = pipeline._analyze_cached(filename, content, {}, True, preloaded=(frame, report))
            record["clean_seconds"] = round(time.perf_counter() - start, 4)
            start = time.perf_counter()
            metrics = pipeline._metrics_from_clean_result(filename, cleaned, None, None)
            record["metrics_seconds"] = round(time.perf_counter() - start, 4)
            record["rows_preserved"] = len(cleaned["_df_limpio"]) == rows
            actual_total = metrics["kpis"]["ingresos_totales"]["valor"]
            record["independent_total_matches"] = abs(actual_total - expected_total) < 0.01
            record["peak_rss_mb"] = round(max(peaks[start_index:] + [process.memory_info().rss]) / 1024**2, 2)
            record["rss_growth_mb"] = round((process.memory_info().rss - before) / 1024**2, 2)

            def cached_analysis(_):
                start = time.perf_counter()
                pipeline._analyze_cached(filename, content, {}, True)
                return time.perf_counter() - start

            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=10) as executor:
                latencies = list(executor.map(cached_analysis, range(50)))
            record["cached_50_requests_10_threads_seconds"] = round(time.perf_counter() - start, 4)
            record["cached_p95_ms"] = round(sorted(latencies)[int(len(latencies) * 0.95) - 1] * 1000, 3)
            record["cached_median_ms"] = round(statistics.median(latencies) * 1000, 3)
            result["workloads"].append(record)
            print(json.dumps(record), flush=True)
    finally:
        sample_stop.set()
        sampler.join()
    result["peak_process_rss_mb"] = round(max(peaks + [process.memory_info().rss]) / 1024**2, 2)
    result["safety"] = {"production_requests": 0, "uploaded_files": 0, "customer_files_read": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Evidence: {args.output}", flush=True)


if __name__ == "__main__":
    main()

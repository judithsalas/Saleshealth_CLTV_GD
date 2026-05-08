"""
Saleshealth CLTV · Orquestador del ETL.

Punto único de entrada para ejecutar las distintas fases del pipeline.

Uso:
    python run.py --bootstrap        # crea BD nueva + DDL
    python run.py --extract          # copia origen → stg
    python run.py --transform        # stg → dwh (dimensiones + hechos)
    python run.py --validate         # checks de calidad
    python run.py --cltv             # CLTV BG/NBD + Gamma-Gamma
    python run.py --cluster          # K-Means con triple validación + UMAP
    python run.py --all              # ejecuta TODO en orden

Ejemplos:
    python run.py --bootstrap --extract     # primera vez
    python run.py --transform               # solo recalcular DWH
    python run.py --all                     # pipeline entero
"""
from __future__ import annotations

import argparse
import sys
import time

# ----------------------------------------------------------------------------
#  Fases en orden de ejecución
# ----------------------------------------------------------------------------
PHASES = [
    ("bootstrap",   "etl.bootstrap",            "Crea la BD y aplica el DDL"),
    ("extract",     "etl.extract",              "Copia origen → schema stg"),
    ("transform",   "etl.transform_dimensions", "stg → dwh (dimensiones)"),
    ("transform2",  "etl.transform_facts",      "stg → dwh (hechos)"),
    ("validate",    "etl.validate",             "Checks de calidad"),
    ("cltv",        "etl.cltv",                 "CLTV BG/NBD + Gamma-Gamma"),
    ("cluster",     "etl.cluster",              "K-Means + triple validación + UMAP"),
]


# Flags públicos (--transform expande a las dos fases de transformación)
FLAG_TO_PHASES: dict[str, list[str]] = {
    "bootstrap": ["bootstrap"],
    "extract":   ["extract"],
    "transform": ["transform", "transform2"],
    "validate":  ["validate"],
    "cltv":      ["cltv"],
    "cluster":   ["cluster"],
}


def run_phase(name: str, module_name: str, description: str) -> bool:
    print(f"\n{'#' * 70}")
    print(f"#  Fase: {name.upper()} — {description}")
    print(f"{'#' * 70}")

    t0 = time.perf_counter()
    try:
        module = __import__(module_name, fromlist=["main"])
        rc = module.main()
        elapsed = time.perf_counter() - t0
        if rc != 0:
            print(f"\n[FALLO] Fase '{name}' en {elapsed:.2f}s (rc={rc})")
            return False
        print(f"\n[OK]    Fase '{name}' completada en {elapsed:.2f}s")
        return True
    except Exception as exc:                                       # noqa: BLE001
        elapsed = time.perf_counter() - t0
        print(f"\n[FALLO] Fase '{name}' en {elapsed:.2f}s")
        print(f"        {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquestador del ETL de Saleshealth CLTV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Uso:", 1)[-1] if __doc__ else "",
    )
    for flag, phase_names in FLAG_TO_PHASES.items():
        first = phase_names[0]
        desc = next(d for n, _, d in PHASES if n == first)
        parser.add_argument(f"--{flag}", action="store_true", help=desc)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ejecuta todas las fases en orden",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.all:
        phases_to_run = PHASES
    else:
        active: list[str] = []
        for flag, phase_names in FLAG_TO_PHASES.items():
            if getattr(args, flag, False):
                active.extend(phase_names)
        phases_to_run = [
            (n, m, d) for n, m, d in PHASES if n in active
        ]

    if not phases_to_run:
        print(
            "ERROR: hay que indicar al menos una fase.\n\n"
            "Ejemplo:  python run.py --bootstrap --extract\n"
            "         python run.py --all\n\n"
            "Fases disponibles:"
        )
        for flag in FLAG_TO_PHASES:
            first = FLAG_TO_PHASES[flag][0]
            desc = next(d for n, _, d in PHASES if n == first)
            print(f"  --{flag:<10}  {desc}")
        return 1

    t0 = time.perf_counter()
    print(f"\nEjecutando {len(phases_to_run)} fase(s)...")

    for name, module, desc in phases_to_run:
        if not run_phase(name, module, desc):
            return 1

    total = time.perf_counter() - t0
    print(f"\n{'#' * 70}")
    print(f"#  Pipeline completado en {total:.2f}s")
    print(f"{'#' * 70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

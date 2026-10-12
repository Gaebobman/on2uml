"""on2uml command line.

    on2uml ONTOLOGY.ttl -o out.png [options]     one diagram
    on2uml --config views.yaml [--only NAME]     every view in a config file
"""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .diff import compare
from .model import load
from .perclass import run as run_per_class
from .spec import ViewSpec, generate
from .standards import parse_namespace_args


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="on2uml",
        description="Render an OWL ontology (Turtle) as UML-style class diagram images.",
    )
    p.add_argument("ttl", nargs="?", help="ontology file (.ttl); omit with --config")
    p.add_argument("-o", "--output", help="output path; extension picks the format (.png/.svg/.puml)")
    p.add_argument("--config", help="views.yaml describing several diagrams")
    p.add_argument("--only", action="append", default=[], metavar="NAME",
                   help="with --config: render only these views (per_class = the per-class block); repeatable")

    view = p.add_argument_group("view")
    view.add_argument("--focus", action="append", default=[], metavar="CLASS",
                      help="centre on this class (IRI, local name or label); repeatable")
    view.add_argument("--depth", type=int, default=1, help="hops around --focus (default: 1)")
    view.add_argument("--subtree", action="append", default=[], metavar="CLASS",
                      help="draw this class and all its subclasses; repeatable")
    view.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                      help="drop classes whose IRI contains PATTERN, or whose name/label equals it; repeatable")
    view.add_argument("--collapse", type=int, metavar="N",
                      help="fold plain leaf subclasses into their parent box when a parent has more than N")

    look = p.add_argument_group("content")
    look.add_argument("--names", choices=["both", "label", "name"], default="both",
                      help="show rdfs:label, local name, or both (default)")
    look.add_argument("--lang", default="ko", help="preferred label/comment language (default: ko)")
    look.add_argument("--notes", choices=["none", "focus", "all"], default="focus",
                      help="draw rdfs:comment as notes for none / --focus classes (default) / all classes")
    look.add_argument("--no-attributes", action="store_true", help="hide datatype properties")
    look.add_argument("--no-inherited", action="store_true",
                      help="don't show what --focus classes inherit from ancestors outside the diagram")
    look.add_argument("--no-standards", action="store_true",
                      help="don't mark classes from standard ontologies (BFO, IOF, ...) with «stereotypes»")
    look.add_argument("--namespace", action="append", default=[], metavar="PREFIX=NAME",
                      help="treat IRIs starting with PREFIX as standard ontology NAME; repeatable")
    look.add_argument("--individuals", action="store_true", help="draw named individuals")
    look.add_argument("--color-by", choices=["none", "source"], default="none",
                      help="fill classes by dcterms:source")
    look.add_argument("--direction", choices=["tb", "lr"], default="tb")
    look.add_argument("--title")
    look.add_argument("--font", help='font family for the image, e.g. "Noto Sans CJK KR"')
    look.add_argument("--no-legend", action="store_true", help="don't explain the notation in a legend")

    extra = p.add_argument_group("annotations")
    extra.add_argument("--overlay", help="YAML with report-only notes/colors/hidden classes")
    extra.add_argument("--compare", metavar="OLD_TTL", help="highlight changes against an older version")

    p.add_argument("--plantuml-jar", help="path to plantuml.jar (or set PLANTUML_JAR)")
    p.add_argument("--keep-puml", action="store_true", help="keep the .puml next to the image")
    return p.parse_args(argv)


def _report(name: str | None, result, warnings: list[str]) -> None:
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    prefix = f"[{name}] " if name else ""
    print(f"{prefix}{result.path}  ({result.classes} classes)")


def _run_config(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    names = list(cfg.views) + (["per_class"] if cfg.per_class else [])
    unknown = sorted(set(args.only) - set(names))
    if unknown:
        print(f"error: no such view: {', '.join(unknown)} (have: {', '.join(names)})", file=sys.stderr)
        return 2
    ns = {**cfg.namespaces, **parse_namespace_args(args.namespace)}
    model = load(cfg.ontology, lang=cfg.lang, namespaces=ns)
    for w in model.warnings:
        print(f"warning: {w}", file=sys.stderr)
    diff = compare(load(cfg.compare, lang=cfg.lang, namespaces=ns), model) if cfg.compare else None
    if diff:
        print(f"diff vs {cfg.compare.name}: {diff.summary()}", file=sys.stderr)

    failed = 0
    for name, spec in cfg.views.items():
        if args.only and name not in args.only:
            continue
        try:
            result = generate(spec, model, diff, args.plantuml_jar)
        except (ValueError, RuntimeError) as e:
            print(f"[{name}] error: {e}", file=sys.stderr)
            failed += 1
            continue
        _report(name, result, result.warnings)

    if cfg.per_class and (not args.only or "per_class" in args.only):
        try:
            rep = run_per_class(cfg.per_class, model, diff, args.plantuml_jar, ontology_name=cfg.ontology.name)
        except (ValueError, RuntimeError) as e:
            print(f"[per_class] error: {e}", file=sys.stderr)
            return 1
        for w in rep.warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(f"[per_class] {cfg.per_class.output_dir}  ({rep.summary()})")
        for title, items in (("added", rep.added), ("changed", rep.changed), ("removed", rep.removed)):
            if items:
                shown = ", ".join(items[:15]) + (f" … (+{len(items) - 15})" if len(items) > 15 else "")
                print(f"  {title}: {shown}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.config:
            if args.ttl or args.output:
                print("error: --config takes the ontology and outputs from the file; drop TTL and -o", file=sys.stderr)
                return 2
            return _run_config(args)
        if not args.ttl or not args.output:
            print("error: give ONTOLOGY.ttl and -o OUTPUT, or --config views.yaml", file=sys.stderr)
            return 2

        spec = ViewSpec(
            output=args.output,
            focus=args.focus,
            depth=args.depth,
            subtree=args.subtree,
            exclude=args.exclude,
            collapse=args.collapse,
            names=args.names,
            notes=args.notes,
            attributes=not args.no_attributes,
            individuals=args.individuals,
            inherited=not args.no_inherited,
            standards=not args.no_standards,
            color_by=args.color_by,
            direction=args.direction,
            title=args.title,
            font=args.font,
            legend=not args.no_legend,
            overlay=args.overlay,
            keep_puml=args.keep_puml,
        )
        ns = parse_namespace_args(args.namespace)
        model = load(args.ttl, lang=args.lang, namespaces=ns)
        for w in model.warnings:
            print(f"warning: {w}", file=sys.stderr)
        diff = None
        if args.compare:
            diff = compare(load(args.compare, lang=args.lang, namespaces=ns), model)
            print(f"diff: {diff.summary()}", file=sys.stderr)
        result = generate(spec, model, diff, args.plantuml_jar)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1 if isinstance(e, RuntimeError) else 2
    _report(None, result, result.warnings)
    return 0


if __name__ == "__main__":
    sys.exit(main())

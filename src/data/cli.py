"""Command-line entry point for the metrics datastore."""

from __future__ import annotations

import argparse
import sys

from .ingest import find_info_jsons, source_record_from_info_json
from .models import UploadRecord
from .store import DataStore

DEFAULT_DB = "transdub.db"


def _fmt(n: int | None) -> str:
    return "—" if n is None else f"{n:,}"


def _cmd_record_source(store: DataStore, args) -> int:
    paths = find_info_jsons(args.path)
    if not paths:
        print(f"error: no info.json found at {args.path}", file=sys.stderr)
        return 2
    for path in paths:
        rec = source_record_from_info_json(path)
        store.record_source(rec)
        print(f"✓ source {rec.source_id or '?'}  views={_fmt(rec.view_count)}  {rec.title or path.name}")
    return 0


def _cmd_record_upload(store: DataStore, args) -> int:
    store.record_upload(UploadRecord(
        source_id=args.source_id, platform=args.platform, url=args.url,
        title=args.title, view_count=args.views, like_count=args.likes,
        comment_count=args.comments,
    ))
    print(f"✓ upload recorded for {args.source_id} on {args.platform}")
    return 0


def _cmd_list(store: DataStore, args) -> int:
    sources = store.list_sources()
    if not sources:
        print("(no sources recorded)")
        return 0
    for s in sources:
        print(f"{s.source_id:<14} views={_fmt(s.view_count):>12}  likes={_fmt(s.like_count):>10}  {s.title or ''}")
    return 0


def _cmd_show(store: DataStore, args) -> int:
    cmp = store.comparison(args.source_id)
    if cmp.source is None and cmp.upload is None:
        print(f"error: nothing recorded for {args.source_id}", file=sys.stderr)
        return 2
    if cmp.source:
        s = cmp.source
        print(f"source  views={_fmt(s.view_count)}  likes={_fmt(s.like_count)}  ({s.title or ''})")
    if cmp.upload:
        u = cmp.upload
        print(f"upload  views={_fmt(u.view_count)}  likes={_fmt(u.like_count)}  [{u.platform}] {u.url or ''}")
    ratio = cmp.view_ratio()
    if ratio is not None:
        print(f"upload/source views: {ratio:.1%}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transdub-data",
        description="Store and compare source vs. re-upload video metrics.",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite path (default: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_src = sub.add_parser("record-source", help="ingest source metrics from info.json (file or dir)")
    p_src.add_argument("path")
    p_src.set_defaults(func=_cmd_record_source)

    p_up = sub.add_parser("record-upload", help="record metrics for one of our re-uploads")
    p_up.add_argument("--source-id", required=True)
    p_up.add_argument("--platform", required=True)
    p_up.add_argument("--url")
    p_up.add_argument("--title")
    p_up.add_argument("--views", type=int)
    p_up.add_argument("--likes", type=int)
    p_up.add_argument("--comments", type=int)
    p_up.set_defaults(func=_cmd_record_upload)

    p_list = sub.add_parser("list", help="list latest snapshot per source")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="compare source vs. upload for a source id")
    p_show.add_argument("source_id")
    p_show.set_defaults(func=_cmd_show)

    args = parser.parse_args(argv)
    with DataStore(args.db) as store:
        return args.func(store, args)


if __name__ == "__main__":
    raise SystemExit(main())

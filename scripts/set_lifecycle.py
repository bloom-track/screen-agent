"""Run ONCE to make Wasabi auto-delete screenshots after N days.

Wasabi charges a 90-day minimum per object, so deleting earlier than ~90
days saves nothing. Default here is 90.

Usage:
    pip install boto3
    python scripts/set_lifecycle.py           # reads keys from config.json
    python scripts/set_lifecycle.py --days 120
"""
import argparse
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import config  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    cfg = config.load()
    if not cfg.get("wasabi_bucket"):
        sys.exit("No wasabi_bucket in config.json - configure the app first.")

    s3 = boto3.client(
        "s3",
        endpoint_url=cfg["wasabi_endpoint"],
        aws_access_key_id=cfg["wasabi_access_key"],
        aws_secret_access_key=cfg["wasabi_secret_key"],
        region_name=cfg.get("wasabi_region", "us-east-1"),
    )
    prefix = str(cfg.get("key_prefix", "screenshots")).strip("/") + "/"
    s3.put_bucket_lifecycle_configuration(
        Bucket=cfg["wasabi_bucket"],
        LifecycleConfiguration={
            "Rules": [{
                "ID": f"expire-screenshots-{args.days}d",
                "Status": "Enabled",
                "Filter": {"Prefix": prefix},
                "Expiration": {"Days": args.days},
            }]
        },
    )
    print(f"Lifecycle set: delete '{prefix}*' after {args.days} days "
          f"in bucket {cfg['wasabi_bucket']}.")


if __name__ == "__main__":
    main()

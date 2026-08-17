"""Cloudflare Workers deployment via Wrangler."""

import os
import json
import subprocess
from pathlib import Path


def create_wrangler_config(
    name: str,
    main: str = "src/worker.py",
    account_id: str = "",
    zone_id: str = "",
    routes: list = None,
    env_vars: dict = None,
) -> dict:
    """Generate wrangler.toml config for a Python Worker."""
    config = {
        "name": name,
        "type": "service",
        "main": main,
        "compatibility_date": "2024-06-03",
    }
    
    if account_id:
        config["account_id"] = account_id
    
    if zone_id:
        config["zone_id"] = zone_id
    
    if routes:
        config["routes"] = [
            {
                "pattern": r,
                "zone_name": "wildeboer.legal",  # change as needed
            }
            for r in routes
        ]
    
    if env_vars:
        config["env"] = {"production": {"vars": env_vars}}
    
    config["build"] = {
        "command": "uv pip install -r requirements.txt",
        "cwd": ".",
    }
    
    return config


def write_wrangler_config(config: dict, output_path: str = "wrangler.toml"):
    """Write wrangler.toml (TOML format)."""
    import tomllib
    try:
        import tomli_w
    except ImportError:
        subprocess.run(["pip", "install", "tomli_w"], check=True)
        import tomli_w
    
    Path(output_path).write_bytes(tomli_w.dumps(config))
    print(f"Written {output_path}")


def deploy_to_cloudflare(
    env: str = "production",
    dry_run: bool = False,
) -> dict:
    """Deploy Worker to Cloudflare."""
    cmd = ["wrangler", "deploy"]
    if dry_run:
        cmd.append("--dry-run")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return {
                "status": "deployed",
                "output": result.stdout,
            }
        else:
            return {
                "status": "deployment_failed",
                "error": result.stderr,
            }
    except Exception as exc:
        return {
            "status": "deployment_error",
            "error": str(exc),
        }


def get_cloudflare_kv_namespace(name: str, env: str = "production") -> str:
    """Get KV namespace ID for Langfuse trace storage."""
    cmd = ["wrangler", "kv:namespace", "list"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        namespaces = json.loads(result.stdout)
        for ns in namespaces:
            if ns["title"] == name:
                return ns["id"]
    except Exception:
        pass
    return ""

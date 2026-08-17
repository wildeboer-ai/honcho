"""Vercel deployment helpers for Honcho services."""

import os
import json
import subprocess
from pathlib import Path


def get_vercel_env() -> dict:
    """Get current Vercel environment."""
    try:
        result = subprocess.run(
            ["vercel", "env", "ls"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {"status": "ok", "raw": result.stdout}
    except FileNotFoundError:
        return {"status": "vercel_cli_not_found"}


def create_vercel_config(
    project_name: str,
    build_command: str = "uv build",
    output_dir: str = "dist",
    env_vars: dict = None,
) -> dict:
    """Generate vercel.json config."""
    config = {
        "version": 2,
        "name": project_name,
        "builds": [
            {
                "src": "src/**/*.py",
                "use": "@vercel/python@3.1.1",
                "config": {
                    "maxLambdaSize": "50mb",
                    "runtime": "python3.11",
                },
            }
        ],
        "routes": [
            {
                "src": "/(.*)",
                "dest": "src/api/handler.py",
            }
        ],
        "env": env_vars or {},
        "buildCommand": build_command,
        "outputDirectory": output_dir,
    }
    return config


def write_vercel_config(config: dict, output_path: str = "vercel.json"):
    """Write vercel.json to disk."""
    Path(output_path).write_text(json.dumps(config, indent=2))
    print(f"Written {output_path}")


def deploy_to_vercel(
    project_name: str,
    env_vars: dict = None,
    production: bool = False,
) -> dict:
    """Deploy to Vercel."""
    cmd = ["vercel", "deploy", "--json"]
    if production:
        cmd.append("--prod")
    
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"error": result.stderr, "status": "deployment_failed"}
    except Exception as exc:
        return {"error": str(exc), "status": "deployment_error"}

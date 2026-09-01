"""Configuration management command handlers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_framework.cli.exit_codes import ExitCode
from agent_framework.cli.output import OutputWriter
from agent_framework.config.migration import apply_dotenv_migration, plan_dotenv_migration
from agent_framework.config.schema import FIELD_MAPPINGS, FieldKind
from agent_framework.config.secrets import SecretStore
from agent_framework.config.sources import resolve_settings
from agent_framework.config.store import ConfigPaths, ConfigStore, set_dotted, unset_dotted

_KEY_TO_FIELD = {mapping.key: field for field, mapping in FIELD_MAPPINGS.items()}


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _store_for_scope(paths: ConfigPaths, scope: str) -> ConfigStore:
    return ConfigStore(paths.project_config if scope == "project" else paths.user_config)


def update_config_value(
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
    key: str,
    value: Any,
    scope: str = "user",
) -> None:
    """Validate and atomically persist one non-secret setting."""
    field = _KEY_TO_FIELD.get(key)
    if field is None:
        raise ValueError(f"Unknown config key: {key}")
    if FIELD_MAPPINGS[field].kind is FieldKind.SECRET:
        raise ValueError("Secret fields must be stored through 'myagen auth set'")
    store = _store_for_scope(paths, scope)
    document = store.read()
    set_dotted(document, key, value)
    with tempfile.TemporaryDirectory(prefix="myagen-config-check-") as temp_dir:
        candidate_path = Path(temp_dir) / "config.toml"
        ConfigStore(candidate_path).write(document)
        candidate_paths = ConfigPaths(
            user_config=candidate_path if scope == "user" else paths.user_config,
            project_config=candidate_path if scope == "project" else paths.project_config,
            data_dir=paths.data_dir,
            cache_dir=paths.cache_dir,
        )
        resolve_settings(paths=candidate_paths, secret_store=secret_store)
    store.write(document)


def run_config_command(
    args: Any,
    output: OutputWriter,
    *,
    paths: ConfigPaths,
    secret_store: SecretStore,
) -> ExitCode:
    action = args.config_command
    if action == "path":
        selected = {
            "user": paths.user_config,
            "project": paths.project_config,
        }
        if args.scope == "effective":
            path_data = {key: str(value) for key, value in selected.items()}
            output.success(
                path_data,
                text="\n".join(f"{key}: {value}" for key, value in path_data.items()),
            )
        else:
            path = selected[args.scope]
            output.success(str(path), text=str(path))
        return ExitCode.OK

    store = _store_for_scope(paths, getattr(args, "scope", "user"))
    if action == "init":
        created = store.initialize()
        output.success(
            {"path": str(store.path), "created": created},
            text=(f"Created {store.path}" if created else f"Already exists: {store.path}"),
        )
        return ExitCode.OK

    if action == "import":
        source = ConfigStore(Path(args.path))
        try:
            imported = source.read()
            with tempfile.TemporaryDirectory(prefix="myagen-import-check-") as temp_dir:
                candidate = Path(temp_dir) / "config.toml"
                ConfigStore(candidate).write(imported)
                resolve_settings(
                    paths=ConfigPaths(
                        user_config=candidate,
                        project_config=paths.project_config,
                        data_dir=paths.data_dir,
                        cache_dir=paths.cache_dir,
                    ),
                    secret_store=secret_store,
                )
            if not args.dry_run:
                _store_for_scope(paths, "user").write(imported)
        except (OSError, ValueError, ValidationError) as exc:
            output.error("config_import_failed", str(exc))
            return ExitCode.CONFIG
        output.success(
            {"path": args.path, "dry_run": args.dry_run},
            text=("Import is valid (dry-run)." if args.dry_run else "Configuration imported."),
        )
        return ExitCode.OK

    if action == "export":
        effective = resolve_settings(paths=paths, secret_store=secret_store)
        document: dict[str, Any] = {}
        serialized_settings = effective.settings.model_dump(mode="json")
        for field, mapping in FIELD_MAPPINGS.items():
            if mapping.kind is FieldKind.SECRET:
                continue
            export_value = serialized_settings[field]
            if export_value is not None:
                set_dotted(document, mapping.key, export_value)
        ConfigStore(Path(args.path)).write(document)
        output.success({"path": args.path}, text=f"Exported non-secret config to {args.path}")
        return ExitCode.OK

    if action == "migrate-env":
        dotenv_path = Path(args.path)
        try:
            items = plan_dotenv_migration(dotenv_path)
            if not args.dry_run:
                apply_dotenv_migration(items, paths=paths, secret_store=secret_store)
        except (OSError, ValueError, ValidationError) as exc:
            output.error("env_migration_failed", str(exc))
            return ExitCode.CONFIG
        report = [
            {
                "env": item.env_key,
                "destination": item.destination,
                "secret": item.secret,
            }
            for item in items
        ]
        output.success(
            report,
            text="\n".join(
                f"{item['env']} -> {item['destination']}"
                + (" (secret)" if item["secret"] else "")
                for item in report
            ),
        )
        return ExitCode.OK

    if action in {"set", "unset"}:
        mapping_field = _KEY_TO_FIELD.get(args.key)
        if mapping_field is None:
            output.error("unknown_config_key", f"Unknown config key: {args.key}")
            return ExitCode.USAGE
        mapping = FIELD_MAPPINGS[mapping_field]
        if mapping.kind is FieldKind.SECRET:
            output.error(
                "secret_requires_auth",
                "Secrets cannot be written to TOML or passed as config values.",
                hint="Use 'myagen auth set <provider>' instead.",
            )
            return ExitCode.USAGE
        document = store.read()
        if action == "set":
            if args.value is None:
                output.error("missing_value", f"A value is required for {args.key}")
                return ExitCode.USAGE
            try:
                update_config_value(
                    paths=paths,
                    secret_store=secret_store,
                    key=args.key,
                    value=_parse_value(args.value),
                    scope=args.scope,
                )
            except (ValueError, ValidationError) as exc:
                output.error("invalid_config", str(exc))
                return ExitCode.CONFIG
            output.success({"key": args.key, "updated": True}, text=f"Updated {args.key}")
            return ExitCode.OK
        else:
            unset_dotted(document, args.key)
        try:
            with tempfile.TemporaryDirectory(prefix="myagen-config-check-") as temp_dir:
                candidate_path = Path(temp_dir) / "config.toml"
                ConfigStore(candidate_path).write(document)
                candidate_paths = ConfigPaths(
                    user_config=(candidate_path if args.scope == "user" else paths.user_config),
                    project_config=(
                        candidate_path if args.scope == "project" else paths.project_config
                    ),
                    data_dir=paths.data_dir,
                    cache_dir=paths.cache_dir,
                )
                resolve_settings(paths=candidate_paths, secret_store=secret_store)
            store.write(document)
        except (ValueError, ValidationError) as exc:
            output.error("invalid_config", str(exc))
            return ExitCode.CONFIG
        output.success({"key": args.key, "updated": True}, text=f"Updated {args.key}")
        return ExitCode.OK

    try:
        effective = resolve_settings(paths=paths, secret_store=secret_store)
    except (ValueError, ValidationError) as exc:
        output.error("invalid_config", str(exc))
        return ExitCode.CONFIG

    if action == "validate":
        output.success({"valid": True}, text="Configuration is valid.")
        return ExitCode.OK
    if action in {"get", "list"}:
        fields = [
            _KEY_TO_FIELD[args.key]
        ] if action == "get" and args.key in _KEY_TO_FIELD else list(FIELD_MAPPINGS)
        if action == "get" and args.key not in _KEY_TO_FIELD:
            output.error("unknown_config_key", f"Unknown config key: {args.key}")
            return ExitCode.USAGE
        data: dict[str, Any] = {}
        for field in fields:
            mapping = FIELD_MAPPINGS[field]
            value: Any = getattr(effective.settings, field)
            if mapping.kind is FieldKind.SECRET:
                value = "********" if value else None
            if getattr(args, "source", False):
                data[mapping.key] = {"value": value, "source": effective.sources[field]}
            else:
                data[mapping.key] = value
        if action == "get":
            value = data[args.key]
            output.success(value, text=json.dumps(value, ensure_ascii=False, default=str))
        else:
            text = "\n".join(
                f"{key} = {json.dumps(value, ensure_ascii=False, default=str)}"
                for key, value in sorted(data.items())
            )
            output.success(data, text=text)
        return ExitCode.OK

    output.error("unsupported_config_command", f"Unsupported config command: {action}")
    return ExitCode.USAGE


__all__ = ["run_config_command", "update_config_value"]

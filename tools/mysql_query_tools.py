# tools/mysql_query.py
# MySQL MCP 工具：支持跨库操作（可选）并与 mcp-server 集成
#
# 说明（中文）：
# - 本工具允许管理多数据库连接配置（通过 .env 指定多个 MYSQL_<NAME>_* 条目，或使用 MYSQL_DEFAULT_*）。
# - 新增支持：可选开启跨库/全库访问（MYSQL_ALLOW_ALL_DATABASES=true），启用后工具可以列出所有数据库并在任意数据库上执行查询/写操作（前提是所配置的 MySQL 帐号本身具有相应权限）。
# - 默认情况下跨库访问被禁用（安全考虑）。若需启用，请在 .env 中设置 MYSQL_ALLOW_ALL_DATABASES=true，并确保所用 MySQL 帐号有全库权限（GRANT 权限由 DBA 管理，工具无法提升权限）。
# - 支持动作：test_connection, list_databases, list_tables, table_schema, query, execute
# - 安全保护：写操作（INSERT/UPDATE/DELETE/DDL 等）默认受 ALLOW_DB_MUTATIONS=false 保护；要执行写操作还需在 .env 中设置 ALLOW_DB_MUTATIONS=true。
# - 查询返回：Markdown + JSON（preview + 完整 JSON 截断），避免超大输出。

# -----------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Tuple
import json
import re

from tools.config import get as cfg_get, as_dict as cfg_as_dict

# Try importing pymysql then mysql.connector
_DB_DRIVER = None
try:
    import pymysql  # type: ignore
    _DB_DRIVER = "pymysql"
except Exception:
    try:
        import mysql.connector as mysql_connector  # type: ignore
        _DB_DRIVER = "mysqlconnector"
    except Exception:
        _DB_DRIVER = None

# Basic token safety check for connection names
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

def _is_safe_name(n: str) -> bool:
    return bool(_NAME_RE.fullmatch(n))

def _get_all_env() -> Dict[str, str]:
    try:
        return cfg_as_dict()
    except Exception:
        return {}

def _resolve_connection_prefix(name: Optional[str]) -> str:
    if not name:
        return "DEFAULT"
    n = str(name).strip()
    if n.lower() == "default":
        return "DEFAULT"
    fixed = re.sub(r"[^A-Za-z0-9]", "_", n).upper()
    return fixed

def _get_connection_config(name: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    读取指定连接配置。数据库名 (database) 可选，若希望跨库操作请在 .env 中启用 MYSQL_ALLOW_ALL_DATABASES=true。
    返回 (config_dict or None, error_message or None)
    """
    prefix = _resolve_connection_prefix(name)
    env = _get_all_env()

    def kv(key: str) -> Optional[str]:
        return env.get(key)

    host = kv(f"MYSQL_{prefix}_HOST") or kv("MYSQL_HOST") or kv("MYSQL_DEFAULT_HOST")
    port = kv(f"MYSQL_{prefix}_PORT") or kv("MYSQL_PORT") or kv("MYSQL_DEFAULT_PORT")
    user = kv(f"MYSQL_{prefix}_USER") or kv("MYSQL_USER") or kv("MYSQL_DEFAULT_USER")
    password = kv(f"MYSQL_{prefix}_PASSWORD") or kv("MYSQL_PASSWORD") or kv("MYSQL_DEFAULT_PASSWORD")
    # accept both MYSQL_<PREFIX>_DB or MYSQL_<PREFIX>_DATABASE
    database = kv(f"MYSQL_{prefix}_DB") or kv(f"MYSQL_{prefix}_DATABASE") or kv("MYSQL_DATABASE") or kv("MYSQL_DEFAULT_DB") or kv("MYSQL_DEFAULT_DATABASE")
    try:
        timeout = int(kv(f"MYSQL_{prefix}_TIMEOUT") or kv("MYSQL_TIMEOUT") or kv("MYSQL_DEFAULT_TIMEOUT") or 30)
    except Exception:
        timeout = 30

    if not host:
        return None, f"Connection '{name or 'default'}' not configured: no host found in .env (checked MYSQL_{prefix}_HOST / MYSQL_HOST / MYSQL_DEFAULT_HOST)"
    try:
        port_i = int(port) if port else 3306
    except Exception:
        port_i = 3306

    # database may be None or empty string -> treat as None
    if database is not None and str(database).strip() == "":
        database = None

    return {
        "host": host,
        "port": port_i,
        "user": user,
        "password": password,
        "database": database,
        "connect_timeout": timeout
    }, None

def _connect(cfg: Dict[str, Any]):
    if _DB_DRIVER == "pymysql":
        conn = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),  # may be None
            connect_timeout=cfg.get("connect_timeout", 30),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )
        return conn
    elif _DB_DRIVER == "mysqlconnector":
        conn = mysql_connector.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),  # may be None
            connection_timeout=cfg.get("connect_timeout", 30),
        )
        return conn
    else:
        raise RuntimeError("No DB driver available: install pymysql or mysql-connector-python")

def _fetchall_dict(cursor, driver: str) -> List[Dict[str, Any]]:
    if driver == "pymysql":
        return cursor.fetchall()
    else:
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        out = []
        for r in rows:
            out.append({cols[i]: r[i] for i in range(len(cols))})
        return out

def _format_results_preview(rows: List[Dict[str, Any]], limit: int = 20) -> str:
    if not rows:
        return "No rows returned.\n"
    cols = list(rows[0].keys())
    disp = rows[:limit]
    header = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |\n"
    lines = [header, sep]
    for r in disp:
        vals = []
        for c in cols:
            v = r.get(c)
            if v is None:
                vals.append("")
            else:
                s = str(v)
                if len(s) > 200:
                    s = s[:197] + "..."
                vals.append(s.replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |\n")
    footer = ""
    if len(rows) > limit:
        footer = f"\n_Note: showing first {limit} of {len(rows)} rows_\n"
    return "".join(lines) + footer

def _is_write_statement(sql: str) -> bool:
    s = sql.strip().lower()
    return bool(re.match(r"^(insert|update|delete|replace|create|alter|drop|truncate|rename|grant|revoke)\b", s))

class MySQLQueryTool:
    name = "mysql_query"
    aliases = ["mysql", "sql"]
    description = "MySQL数据库查询工具，支持跨库查询和列出所有数据库，写操作受ALLOW_DB_MUTATIONS保护"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["test_connection", "list_databases", "list_tables", "table_schema", "query", "execute"], "default": "test_connection"},
            "connection": {"type": "string"},
            "database": {"type": "string"},   # 可选：指定要操作的数据库（需在 .env 中启用 MYSQL_ALLOW_ALL_DATABASES 才能跨库）
            "table": {"type": "string"},
            "sql": {"type": "string"},
            "params": {"type": "array"},
            "limit": {"type": "integer", "default": 100}
        },
        "required": []
    }

    def run(self, params: Dict[str, Any]) -> str:
        try:
            if not isinstance(params, dict):
                return "Error: params must be an object"

            action = (params.get("action") or "test_connection").strip()
            conn_name = params.get("connection") or "default"
            cfg, err = _get_connection_config(conn_name)
            if err:
                return f"Error: {err}"
            if _DB_DRIVER is None:
                return "Error: no MySQL driver available. Install pymysql or mysql-connector-python."

            # whether global (cross-db) allowed by config
            allow_all = str(cfg_get("MYSQL_ALLOW_ALL_DATABASES") or "false").lower() in ("1", "true", "yes", "y")

            # requested database (may be None)
            requested_db = params.get("database")
            if requested_db is not None and str(requested_db).strip() == "":
                requested_db = None

            # If requested_db differs from configured cfg['database'] and allow_all false -> deny
            cfg_db = cfg.get("database")
            if requested_db and (cfg_db != requested_db):
                if not allow_all:
                    return "Error: cross-database operations are disabled by configuration. Set MYSQL_ALLOW_ALL_DATABASES=true in .env to enable (and ensure DB user has privileges)."

            if action == "test_connection":
                return self._action_test_connection(cfg)
            elif action == "list_databases":
                # only allowed if server credentials permit; config-level allow_all not strictly required for listing,
                # but we still respect allow_all to avoid accidental exposure
                if not allow_all:
                    return "Error: listing all databases is disabled by configuration. Set MYSQL_ALLOW_ALL_DATABASES=true to allow."
                return self._action_list_databases(cfg)
            elif action == "list_tables":
                table_db = requested_db or cfg_db
                if not table_db:
                    return "Error: target database not specified and no default configured (set MYSQL_DEFAULT_DB or provide 'database' param)."
                return self._action_list_tables(cfg, table_db)
            elif action == "table_schema":
                table = params.get("table")
                if not table:
                    return "Error: 'table' parameter required for table_schema"
                table_db = requested_db or cfg_db
                if not table_db:
                    return "Error: target database not specified and no default configured"
                return self._action_table_schema(cfg, table_db, table)
            elif action == "query":
                sql = params.get("sql")
                if not sql:
                    return "Error: 'sql' parameter required for query"
                p = params.get("params") or []
                limit = int(params.get("limit") or 100)
                # if requested_db provided and allowed, set default DB before running
                return self._action_query(cfg, sql, p, limit, requested_db, allow_all)
            elif action == "execute":
                sql = params.get("sql")
                if not sql:
                    return "Error: 'sql' parameter required for execute"
                p = params.get("params") or []
                allow_mut = str(cfg_get("ALLOW_DB_MUTATIONS") or "false").lower() in ("1", "true", "yes", "y")
                if not allow_mut and _is_write_statement(sql):
                    return "Error: write operations are disabled by configuration (ALLOW_DB_MUTATIONS=false). Set ALLOW_DB_MUTATIONS=true in .env to allow."
                # check cross-db
                if requested_db and (cfg.get("database") != requested_db) and not allow_all:
                    return "Error: cross-database execute disabled by configuration. Set MYSQL_ALLOW_ALL_DATABASES=true to enable."
                return self._action_execute(cfg, sql, p, requested_db, allow_all)
            else:
                return f"Error: unknown action: {action}"
        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _action_test_connection(self, cfg: Dict[str, Any]) -> str:
        try:
            conn = _connect(cfg)
            try:
                cur = conn.cursor()
                cur.execute("SELECT VERSION() as v")
                row = None
                if _DB_DRIVER == "pymysql":
                    row = cur.fetchone()
                else:
                    r = cur.fetchone()
                    if r:
                        desc = [d[0] for d in cur.description]
                        row = {desc[i]: r[i] for i in range(len(desc))}
                ver = row.get("v") if isinstance(row, dict) else str(row)
                return f"# Test Connection\n\n- Host: {cfg.get('host')}:{cfg.get('port')}\n- Database: {cfg.get('database') or '(none specified)'}\n- OK - version: `{ver}`\n"
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return f"Error: connection failed: {e}"

    def _action_list_databases(self, cfg: Dict[str, Any]) -> str:
        try:
            conn = _connect(cfg)
            try:
                cur = conn.cursor()
                cur.execute("SHOW DATABASES")
                rows = _fetchall_dict(cur, _DB_DRIVER)
                names = []
                for r in rows:
                    if isinstance(r, dict):
                        vals = list(r.values())
                        if vals:
                            names.append(str(vals[0]))
                    elif isinstance(r, (list, tuple)):
                        if r:
                            names.append(str(r[0]))
                md = "# Databases\n\n" + "\n".join([f"- {n}" for n in names]) + "\n"
                return md
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return f"Error: list_databases failed: {e}"

    def _action_list_tables(self, cfg: Dict[str, Any], database: str) -> str:
        try:
            conn = _connect(cfg)
            try:
                cur = conn.cursor()
                # Use fully qualified SHOW TABLES FROM `db`
                cur.execute(f"SHOW TABLES FROM `{database}`")
                rows = _fetchall_dict(cur, _DB_DRIVER)
                names = []
                for r in rows:
                    if isinstance(r, dict):
                        vals = list(r.values())
                        if vals:
                            names.append(str(vals[0]))
                    elif isinstance(r, (list, tuple)):
                        if r:
                            names.append(str(r[0]))
                md = f"# Tables in `{database}`\n\n" + "\n".join([f"- {n}" for n in names]) + "\n"
                return md
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return f"Error: list_tables failed: {e}"

    def _action_table_schema(self, cfg: Dict[str, Any], database: str, table: str) -> str:
        try:
            conn = _connect(cfg)
            try:
                cur = conn.cursor()
                # SHOW CREATE TABLE `db`.`table`
                cur.execute(f"SHOW CREATE TABLE `{database}`.`{table}`")
                rows = cur.fetchall()
                if not rows:
                    return f"No create info for table {database}.{table}"
                if isinstance(rows[0], dict):
                    cs = None
                    for v in rows[0].values():
                        if isinstance(v, str) and "CREATE TABLE" in v.upper():
                            cs = v
                            break
                    if not cs:
                        cs = json.dumps(rows[0])
                else:
                    cs = rows[0][1] if len(rows[0]) > 1 else str(rows[0])
                md = f"# Schema for {database}.{table}\n\n```\n{cs}\n```\n"
                return md
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return f"Error: table_schema failed: {e}"

    def _action_query(self, cfg: Dict[str, Any], sql: str, params: List[Any], limit: int, requested_db: Optional[str], allow_all: bool) -> str:
        try:
            conn = _connect(cfg)
            try:
                cur = conn.cursor()
                # if requested_db specified and allowed, set default DB
                if requested_db:
                    try:
                        # pymysql has select_db, mysql.connector support setting database via cursor.execute("USE db")
                        if _DB_DRIVER == "pymysql":
                            conn.select_db(requested_db)
                        else:
                            cur.execute(f"USE `{requested_db}`")
                    except Exception as e:
                        return f"Error: failed to set database to {requested_db}: {e}"

                cur.execute(sql, params)
                rows = _fetchall_dict(cur, _DB_DRIVER)
                total = len(rows) if isinstance(rows, list) else 0
                preview = _format_results_preview(rows, limit=min(limit, 50))
                json_full = ""
                try:
                    json_full = json.dumps(rows, ensure_ascii=False, default=str, indent=2)
                except Exception:
                    json_full = str(rows)[:2000]
                md = f"# Query Result (host: {cfg.get('host')}:{cfg.get('port')}, db: {requested_db or cfg.get('database') or '(none specified)'})\n\n"
                md += f"**SQL:**\n```\n{sql}\n```\n\n"
                md += f"**Params:** `{params}`\n\n"
                md += f"**Rows returned:** {total}\n\n"
                md += "**Preview:**\n\n"
                md += preview + "\n"
                md += "\n" + "```json\n" + (json_full[:20000]) + "\n```\n"
                return md
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return f"Error: query failed: {e}"

    def _action_execute(self, cfg: Dict[str, Any], sql: str, params: List[Any], requested_db: Optional[str], allow_all: bool) -> str:
        try:
            conn = _connect(cfg)
            try:
                cur = conn.cursor()
                if requested_db:
                    try:
                        if _DB_DRIVER == "pymysql":
                            conn.select_db(requested_db)
                        else:
                            cur.execute(f"USE `{requested_db}`")
                    except Exception as e:
                        return f"Error: failed to set database to {requested_db}: {e}"
                cur.execute(sql, params)
                try:
                    conn.commit()
                except Exception:
                    pass
                affected = None
                try:
                    if hasattr(cur, "rowcount"):
                        affected = cur.rowcount
                except Exception:
                    affected = None
                return f"# Execute\n\n- SQL: ``{sql}``\n- Params: `{params}`\n- Rows affected: {affected}\n"
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return f"Error: execute failed: {e}"

# module-level tool object
tool = MySQLQueryTool()
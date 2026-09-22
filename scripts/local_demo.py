"""Manage only VoxERP's private local ERP clone; never target a remote server."""
import argparse
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local-demo'
SOCKET = STATE / 'mysql.sock'
DATABASE = 'ramco_academic_system'
PORT = 3307
MODEL_REVISION = '475b9088d29754a3379866cf5aeb6b41acd313c2'


def binary(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'Missing prerequisite: {name}')
    return path


def sql(statement=None, source=None):
    command = [binary('mariadb'), '--no-defaults', '--protocol=socket',
               f'--socket={SOCKET}', '-u', 'root']
    # Credentials/SQL and dump contents never appear in command arguments/logs.
    result = subprocess.run(command, input=statement.encode() if statement else None,
                            stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Local SQL operation failed; details suppressed to protect dump data.')
    return result.stdout.decode()


def start():
    if not (STATE / 'data/mysql').is_dir():
        raise RuntimeError('Run init with the authorized dump first.')
    # An interrupted filesystem copy can retain InnoDB data while truncating
    # its table definitions. MariaDB starts, but reads then fail with error 1033.
    empty_tables = [path for path in (STATE / 'data').rglob('*')
                    if path.is_file() and path.suffix in {'.frm', '.ibd'}
                    and path.stat().st_size == 0]
    if empty_tables:
        raise RuntimeError(
            f'Local clone has {len(empty_tables)} empty table files. '
            'Preserve this clone and recover from an intact backup or the '
            'authorized SQL dump before starting MariaDB.')
    if SOCKET.exists():
        sql('SELECT 1;')
        print('Local MariaDB is already running.')
        return
    with (STATE / 'server.log').open('ab') as log:
        process = subprocess.Popen([
            binary('mariadbd'), '--no-defaults', f'--datadir={STATE / "data"}',
            f'--socket={SOCKET}', f'--pid-file={STATE / "mysql.pid"}',
            '--bind-address=127.0.0.1', f'--port={PORT}', '--skip-log-bin',
            '--local-infile=0', '--skip-name-resolve', '--read-only=1',
        ], stdout=log, stderr=log, start_new_session=True)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('Local MariaDB exited; inspect .local-demo/server.log.')
        if SOCKET.exists():
            try:
                sql('SELECT 1;')
                print(f'Local MariaDB ready on 127.0.0.1:{PORT}.')
                return
            except RuntimeError:
                pass
        time.sleep(.2)
    raise RuntimeError('Local MariaDB startup timed out; inspect .local-demo/server.log.')


def initialize(dump):
    dump = Path(dump).expanduser().resolve(strict=True)
    if not dump.is_file():
        raise RuntimeError('Dump must be a regular file.')
    if STATE.exists():
        raise RuntimeError('Refusing to overwrite existing .local-demo; use start/run. Preserve it for recovery.')
    # Verify prerequisites before creating state. No system service is changed.
    for name in ('mariadb', 'mariadbd', 'mariadb-install-db'):
        binary(name)
    STATE.mkdir(mode=0o700)
    with (STATE / 'initialize.log').open('wb') as log:
        subprocess.run([binary('mariadb-install-db'), '--no-defaults',
                        f'--datadir={STATE / "data"}', '--auth-root-authentication-method=normal',
                        '--skip-test-db'], stdout=log, stderr=log, check=True)
    start()
    restore(dump)


def restore(dump):
    """Resume after initialization/start failure, only if ERP does not exist."""
    dump = Path(dump).expanduser().resolve(strict=True)
    if (STATE / 'environment.json').exists():
        raise RuntimeError('Demo is already initialized; refusing to overwrite it.')
    existing = sql(f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{DATABASE}';")
    if DATABASE in existing:
        raise RuntimeError('ERP database already exists; refusing to overwrite a partial or complete restore.')
    # Remove TCP root identities before importing. Root is private-socket-only;
    # STATE mode 0700 confines that socket to this OS account.
    accounts = sql("SELECT CONCAT(QUOTE(User),'@',QUOTE(Host)) FROM mysql.user "
                   "WHERE User='' OR (User='root' AND Host<>'localhost');")
    for account in accounts.splitlines()[1:]:
        sql(f'DROP USER {account};')
    owner = pwd.getpwuid(os.getuid()).pw_name.replace("\\", "\\\\").replace("'", "''")
    sql(f"ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket AS '{owner}';")
    sql(f'CREATE DATABASE `{DATABASE}`;')
    with dump.open('rb') as source:
        # Select the database while streaming the original dump unchanged.
        result = subprocess.run([binary('mariadb'), '--no-defaults', '--protocol=socket',
                                 f'--socket={SOCKET}', '-u', 'root',
                                 '--init-command=SET SESSION FOREIGN_KEY_CHECKS=0', DATABASE],
                                stdin=source, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        error_path = STATE / 'restore-error.log'
        error_path.write_bytes(result.stderr)
        os.chmod(error_path, 0o600)
        raise RuntimeError('Dump restore failed; clone retained for inspection; no ready credentials created.')
    password = secrets.token_hex(32)
    sql(f"CREATE USER 'voxerp_demo'@'127.0.0.1' IDENTIFIED BY '{password}';"
        f"GRANT SELECT ON `{DATABASE}`.* TO 'voxerp_demo'@'127.0.0.1';")
    config = {'DB_HOST': '127.0.0.1', 'DB_PORT': str(PORT), 'DB_NAME': DATABASE,
              'DB_USER': 'voxerp_demo', 'DB_PASSWORD': password,
              'DJANGO_SECRET_KEY': secrets.token_hex(48)}
    path = STATE / 'environment.json'
    with path.open('x') as handle:
        os.chmod(path, 0o600)
        json.dump(config, handle)
    print('Authorized dump restored; demo account has SELECT only. Credentials saved privately.')


def environment():
    config = json.loads((STATE / 'environment.json').read_text())
    if config['DB_HOST'] != '127.0.0.1' or config['DB_PORT'] != str(PORT):
        raise RuntimeError('Refusing nonlocal demo configuration.')
    return {**os.environ, **config, 'VOXERP_USE_REAL_DB': 'True',
            'VOXERP_APP_DB': str(STATE / 'auth.sqlite3'),
            'VOXERP_ALLOW_REAL_WRITES': 'False', 'VOXERP_INITIALIZE_DATABASE': 'False',
            'VOXERP_OFFLINE_MODE': 'False', 'VOXERP_ENV': 'development',
            'VOXERP_IDENTITY_MODE': 'local_demo',
            'DEBUG': 'True', 'ALLOWED_HOSTS': 'localhost,127.0.0.1,testserver',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action', required=True)
    subs.add_parser('init').add_argument('--dump', required=True)
    subs.add_parser('restore').add_argument('--dump', required=True)
    subs.add_parser('start')
    subs.add_parser('stop')
    run = subs.add_parser('run')
    run.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == 'init':
        initialize(args.dump)
    elif args.action == 'restore':
        restore(args.dump)
    elif args.action == 'start':
        start()
    elif args.action == 'stop':
        sql('SHUTDOWN;')
        print('Local MariaDB stopped; dataset retained.')
    else:
        command = args.command
        if command and command[0] == '--':
            command = command[1:]
        if not command:
            parser.error('run requires a command after --')
        os.chdir(ROOT)
        env = environment()
        if not env.get('VOXERP_GEMMA_MODEL'):
            from huggingface_hub import snapshot_download
            env['VOXERP_GEMMA_MODEL'] = snapshot_download(
                'mlx-community/gemma-4-e4b-it-4bit', revision=MODEL_REVISION,
                local_files_only=True, ignore_patterns=['README.md', '.gitattributes'])
        os.execvpe(command[0], command, env)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)

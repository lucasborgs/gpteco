"""
core/database.py

Camada de persistência do acervo musical e controle de pedidos.
Usa DuckDB como banco local embarcado (arquivo único, sem servidor).

Tabelas:
  dim_musicas       : acervo de músicas baixadas
    - id, artista, musica, file_path, data_inclusao

  dim_pedidos       : histórico de todos os pedidos (aceitos e rejeitados)
    - id, numero, artista, musica, timestamp_pedido, sucesso, motivo_rejeicao
    - Usada para rate limiting (6h) e analytics.

  dim_configuracoes : configurações da rádio (key-value)
    - chave, valor
"""

import duckdb
import os
from datetime import datetime, timedelta
from pathlib import Path

# Localização padrão do arquivo do banco (pode ser sobrescrita via .env)
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent.parent / "data" / "acervo.duckdb"))

# Pasta raiz de músicas — todas as subpastas são escaneadas na inicialização
MUSICAS_DIR = os.getenv(
    "MUSICAS_DIR",
    str(Path(__file__).parent.parent / "workspace" / "musicas"),
)

# Pasta da fila (excluída do índice — conteúdo temporário)
_FILA_ZARA_DIR = os.getenv(
    "FILA_ZARA_DIR",
    str(Path(__file__).parent.parent / "workspace" / "fila_zara"),
)


def _get_connection() -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) o arquivo do banco e retorna a conexão."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return duckdb.connect(DB_PATH)


def init_db() -> None:
    """
    Garante que o schema está criado.
    Seguro para chamar múltiplas vezes (usa IF NOT EXISTS).
    """
    con = _get_connection()
    try:
        con.execute("CREATE SEQUENCE IF NOT EXISTS seq_dim_musicas START 1;")
        con.execute("""
            CREATE TABLE IF NOT EXISTS dim_musicas (
                id            INTEGER   DEFAULT nextval('seq_dim_musicas') PRIMARY KEY,
                artista       VARCHAR   NOT NULL,
                musica        VARCHAR   NOT NULL,
                file_path     VARCHAR   NOT NULL,
                data_inclusao TIMESTAMP DEFAULT current_timestamp
            );
        """)

        con.execute("CREATE SEQUENCE IF NOT EXISTS seq_dim_pedidos START 1;")
        con.execute("""
            CREATE TABLE IF NOT EXISTS dim_pedidos (
                id               INTEGER   DEFAULT nextval('seq_dim_pedidos') PRIMARY KEY,
                numero           VARCHAR   NOT NULL,
                artista          VARCHAR,
                musica           VARCHAR,
                timestamp_pedido TIMESTAMP DEFAULT current_timestamp,
                sucesso          BOOLEAN   DEFAULT TRUE,
                motivo_rejeicao  VARCHAR   DEFAULT NULL
            );
        """)

        # Migração: adiciona colunas novas em bancos existentes (idempotente)
        colunas = {
            row[0]
            for row in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'dim_pedidos'"
            ).fetchall()
        }
        if "sucesso" not in colunas:
            con.execute("ALTER TABLE dim_pedidos ADD COLUMN sucesso BOOLEAN DEFAULT TRUE")
        if "motivo_rejeicao" not in colunas:
            con.execute("ALTER TABLE dim_pedidos ADD COLUMN motivo_rejeicao VARCHAR DEFAULT NULL")

        con.execute("""
            CREATE TABLE IF NOT EXISTS dim_configuracoes (
                chave VARCHAR PRIMARY KEY,
                valor TEXT NOT NULL
            );
        """)

        con.commit()
        print("[DB] Schema inicializado com sucesso.")

        # Seed de configurações padrão (late import evita circular dependency)
        from core import config_radio
        config_radio.seed_defaults()
    finally:
        con.close()


def buscar_musica(artista: str, musica: str) -> str | None:
    """
    Procura no acervo por artista + música (case-insensitive).

    Retorna:
        str  : caminho absoluto do arquivo se encontrado.
        None : se não existir no acervo.
    """
    con = _get_connection()
    try:
        resultado = con.execute("""
            SELECT file_path
            FROM dim_musicas
            WHERE lower(trim(artista)) = lower(trim(?))
              AND lower(trim(musica))  = lower(trim(?))
            LIMIT 1;
        """, [artista, musica]).fetchone()

        if resultado:
            file_path = resultado[0]
            # Valida se o arquivo ainda existe fisicamente
            if os.path.isfile(file_path):
                print(f"[DB] Música encontrada no acervo: {file_path}")
                return file_path
            else:
                print(f"[DB] Registro existe mas arquivo não encontrado: {file_path}")
                return None

        print(f"[DB] Música não encontrada no acervo: '{musica}' - '{artista}'")
        return None
    finally:
        con.close()


def inserir_musica(artista: str, musica: str, file_path: str) -> int:
    """
    Insere um novo registro no acervo após download concluído.

    Args:
        artista   : nome do artista.
        musica    : título da música.
        file_path : caminho absoluto do .mp3 salvo.

    Retorna:
        int : id do registro inserido.

    Raises:
        FileNotFoundError : se o arquivo não existir antes de inserir.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado para inserção: {file_path}")

    con = _get_connection()
    try:
        con.execute("""
            INSERT INTO dim_musicas (artista, musica, file_path, data_inclusao)
            VALUES (?, ?, ?, ?)
        """, [artista.strip(), musica.strip(), file_path, datetime.now()])
        con.commit()

        novo_id = con.execute("SELECT max(id) FROM dim_musicas").fetchone()[0]
        print(f"[DB] Registro inserido com id={novo_id}: '{musica}' - '{artista}'")
        return novo_id
    finally:
        con.close()


def verificar_cooldown(numero: str, horas: int = 6) -> bool:
    """
    Verifica se o número de telefone pode fazer um novo pedido.

    Retorna:
        True  : número nunca pediu ou já passaram pelo menos `horas` horas.
        False : número fez um pedido dentro da janela de cooldown.
    """
    con = _get_connection()
    try:
        resultado = con.execute("""
            SELECT max(timestamp_pedido)
            FROM dim_pedidos
            WHERE numero = ?
              AND sucesso = TRUE
        """, [numero]).fetchone()

        if not resultado or resultado[0] is None:
            return True  # Nunca fez pedido

        ultimo_pedido = resultado[0]
        limite = datetime.now() - timedelta(hours=horas)
        pode_pedir = ultimo_pedido < limite

        if not pode_pedir:
            proxima_vez = ultimo_pedido + timedelta(hours=horas)
            print(f"[DB] Cooldown ativo para {numero}. Próximo pedido após: {proxima_vez.strftime('%H:%M')}")

        return pode_pedir
    finally:
        con.close()


def registrar_pedido(
    numero: str,
    artista: str,
    musica: str,
    sucesso: bool = True,
    motivo_rejeicao: str | None = None,
) -> None:
    """
    Registra um pedido em dim_pedidos (aceito ou rejeitado).

    Args:
        numero          : número de telefone do ouvinte.
        artista         : nome do artista (pode ser "" se não identificado).
        musica          : título da música (pode ser "" se não identificado).
        sucesso         : True se o pedido foi processado com êxito.
        motivo_rejeicao : motivo da rejeição, se houver
                          ('cooldown' | 'inapropriado' | 'nao_flashback' |
                           'nao_identificado' | 'erro_tecnico' | None).
    """
    con = _get_connection()
    try:
        con.execute("""
            INSERT INTO dim_pedidos
                (numero, artista, musica, timestamp_pedido, sucesso, motivo_rejeicao)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            numero,
            artista.strip() if artista else "",
            musica.strip() if musica else "",
            datetime.now(),
            sucesso,
            motivo_rejeicao,
        ])
        con.commit()
        status = "aceito" if sucesso else f"rejeitado ({motivo_rejeicao})"
        print(f"[DB] Pedido {status}: {numero} → '{musica}' - '{artista}'")
    finally:
        con.close()


def indexar_biblioteca() -> int:
    """
    Escaneia MUSICAS_DIR recursivamente e indexa todos os .mp3 no DuckDB.

    - Parseia o nome do arquivo no formato "Artista - Música.mp3".
    - Ignora arquivos já indexados (por file_path) e a pasta fila_zara.
    - Seguro para chamar no startup: só insere o que ainda não está no banco.

    Retorna:
        int : número de novos registros inseridos.
    """
    if not os.path.isdir(MUSICAS_DIR):
        print(f"[DB] MUSICAS_DIR não encontrado, indexação ignorada: {MUSICAS_DIR}")
        return 0

    fila_abs = os.path.abspath(_FILA_ZARA_DIR)
    con = _get_connection()
    novos = 0

    try:
        for root, dirs, files in os.walk(MUSICAS_DIR):
            # Pula a pasta fila_zara (arquivos temporários de pedidos)
            if os.path.abspath(root).startswith(fila_abs):
                dirs.clear()
                continue

            for file in files:
                if not file.lower().endswith(".mp3"):
                    continue

                stem = Path(file).stem
                if " - " not in stem:
                    continue

                artista, musica = stem.split(" - ", 1)
                artista = artista.strip()
                musica = musica.strip()
                if not artista or not musica:
                    continue

                file_path = os.path.join(root, file)

                existe = con.execute(
                    "SELECT 1 FROM dim_musicas WHERE file_path = ?",
                    [file_path],
                ).fetchone()

                if not existe:
                    con.execute("""
                        INSERT INTO dim_musicas (artista, musica, file_path, data_inclusao)
                        VALUES (?, ?, ?, ?)
                    """, [artista, musica, file_path, datetime.now()])
                    novos += 1

        if novos:
            con.commit()

        print(f"[DB] Biblioteca indexada: {novos} novos arquivos registrados.")
        return novos
    finally:
        con.close()


def listar_acervo() -> list[dict]:
    """
    Retorna todos os registros do acervo como lista de dicionários.
    Útil para debug e relatórios.
    """
    con = _get_connection()
    try:
        rows = con.execute("""
            SELECT id, artista, musica, file_path, data_inclusao
            FROM dim_musicas
            ORDER BY data_inclusao DESC;
        """).fetchall()

        return [
            {
                "id": r[0],
                "artista": r[1],
                "musica": r[2],
                "file_path": r[3],
                "data_inclusao": r[4],
            }
            for r in rows
        ]
    finally:
        con.close()

"""
core/database.py

Camada de persistência do acervo musical e controle de pedidos.
Usa PostgreSQL (Supabase) via psycopg2.

Tabelas:
  dim_musicas   : acervo de músicas baixadas
    - id, artista, musica, file_path, data_inclusao

  dim_pedidos   : histórico de todos os pedidos (aceitos e rejeitados)
    - id, numero, artista, musica, timestamp_pedido, sucesso, motivo_rejeicao
    - Usada para rate limiting (6h) e analytics.

  dim_pendencias : pendências de confirmação de transcrição
    - numero, path_ogg, artista_original, musica_original, timestamp_criacao
"""

import os
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras


def _normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação insensível a diacríticos."""
    normalizado = unicodedata.normalize("NFD", texto)
    sem_acentos = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return sem_acentos.lower().strip()


DATABASE_URL: str = os.getenv("DATABASE_URL", "")

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


def _get_connection() -> psycopg2.extensions.connection:
    """Abre e retorna uma conexão com o banco PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    """
    Garante que o schema está criado.
    Seguro para chamar múltiplas vezes (usa IF NOT EXISTS).
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("CREATE SEQUENCE IF NOT EXISTS seq_dim_musicas START 1;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dim_musicas (
                    id            INTEGER   DEFAULT nextval('seq_dim_musicas') PRIMARY KEY,
                    artista       VARCHAR   NOT NULL,
                    musica        VARCHAR   NOT NULL,
                    file_path     VARCHAR   NOT NULL,
                    data_inclusao TIMESTAMP DEFAULT current_timestamp
                );
            """)

            cur.execute("CREATE SEQUENCE IF NOT EXISTS seq_dim_pedidos START 1;")
            cur.execute("""
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

            cur.execute("ALTER TABLE dim_pedidos ADD COLUMN IF NOT EXISTS telefone VARCHAR;")
            cur.execute("ALTER TABLE dim_pedidos ADD COLUMN IF NOT EXISTS genero VARCHAR;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS dim_pendencias (
                    numero            VARCHAR PRIMARY KEY,
                    path_ogg          VARCHAR NOT NULL,
                    artista_original  VARCHAR,
                    musica_original   VARCHAR,
                    timestamp_criacao TIMESTAMP DEFAULT current_timestamp
                );
            """)

            cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")

        con.commit()
        print("[DB] Schema inicializado com sucesso.")
    finally:
        con.close()


def buscar_musica(artista: str, musica: str) -> str | None:
    """
    Procura no acervo por artista + música com normalização de acentos e case.
    Usa unaccent + LOWER no PostgreSQL para filtrar server-side.

    Retorna:
        str  : caminho absoluto do arquivo se encontrado.
        None : se não existir no acervo.
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT file_path FROM dim_musicas
                WHERE unaccent(LOWER(artista)) = unaccent(LOWER(%s))
                  AND unaccent(LOWER(musica))  = unaccent(LOWER(%s))
                LIMIT 1
                """,
                [artista.strip(), musica.strip()],
            )
            row = cur.fetchone()

        if not row:
            print(f"[DB] Música não encontrada no acervo: '{musica}' - '{artista}'")
            return None

        file_path = row[0]

        if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
            print(f"[DB] Música encontrada no acervo: {file_path}")
            return file_path

        if os.path.isfile(file_path):
            os.remove(file_path)
            print(f"[DB] Arquivo corrompido (0 bytes) removido: {file_path}")
        else:
            print(f"[DB] Registro existe mas arquivo não encontrado: {file_path}")
        try:
            with con.cursor() as cur:
                cur.execute("DELETE FROM dim_musicas WHERE file_path = %s", [file_path])
            con.commit()
            print("[DB] Registro inválido removido do acervo — será baixado novamente.")
        except Exception as e:
            print(f"[DB] Erro ao remover registro inválido ({file_path}): {e}")
            try:
                con.rollback()
            except Exception:
                pass
        return None
    finally:
        con.close()


def inserir_musica(artista: str, musica: str, file_path: str) -> int:
    """
    Insere um novo registro no acervo após download concluído.

    Retorna:
        int : id do registro inserido.

    Raises:
        FileNotFoundError : se o arquivo não existir antes de inserir.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado para inserção: {file_path}")

    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("""
                INSERT INTO dim_musicas (artista, musica, file_path, data_inclusao)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, [artista.strip(), musica.strip(), file_path, datetime.now()])
            novo_id = cur.fetchone()[0]
        con.commit()
        print(f"[DB] Registro inserido com id={novo_id}: '{musica}' - '{artista}'")
        return novo_id
    finally:
        con.close()


def verificar_interacao_recente(numero: str, horas: int = 24) -> bool:
    """
    Retorna True se o número teve qualquer interação nas últimas N horas.
    Usado para enviar msg_saudacao apenas uma vez por sessão de 24h.
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("""
                SELECT max(timestamp_pedido)
                FROM dim_pedidos
                WHERE numero = %s
            """, [numero])
            resultado = cur.fetchone()
        if not resultado or resultado[0] is None:
            return False
        return (datetime.now() - resultado[0]) < timedelta(hours=horas)
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
        with con.cursor() as cur:
            cur.execute("""
                SELECT max(timestamp_pedido)
                FROM dim_pedidos
                WHERE numero = %s
                  AND sucesso = TRUE
            """, [numero])
            resultado = cur.fetchone()

        if not resultado or resultado[0] is None:
            return True

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
    genero: str = "",
) -> None:
    """
    Registra um pedido em dim_pedidos (aceito ou rejeitado).
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("""
                INSERT INTO dim_pedidos
                    (numero, artista, musica, timestamp_pedido, sucesso, motivo_rejeicao, genero)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, [
                numero,
                artista.strip() if artista else "",
                musica.strip() if musica else "",
                datetime.now(),
                sucesso,
                motivo_rejeicao,
                genero.strip() if genero else "",
            ])
        con.commit()
        status = "aceito" if sucesso else f"rejeitado ({motivo_rejeicao})"
        print(f"[DB] Pedido {status}: {numero} → '{musica}' - '{artista}'")
    finally:
        con.close()


def atualizar_telefone(numero: str, telefone: str) -> None:
    """
    Preenche a coluna 'telefone' em todos os pedidos de um número LID.
    Chamado em background após a resolução LID → telefone via API WAHA.
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute(
                "UPDATE dim_pedidos SET telefone = %s WHERE numero = %s AND telefone IS NULL",
                [telefone, numero],
            )
        con.commit()
        print(f"[DB] Telefone atualizado para {numero}: {telefone}")
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

                with con.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM dim_musicas WHERE file_path = %s",
                        [file_path],
                    )
                    existe = cur.fetchone()

                if not existe:
                    with con.cursor() as cur:
                        cur.execute("""
                            INSERT INTO dim_musicas (artista, musica, file_path, data_inclusao)
                            VALUES (%s, %s, %s, %s)
                        """, [artista, musica, file_path, datetime.now()])
                    novos += 1

        if novos:
            con.commit()

        print(f"[DB] Biblioteca indexada: {novos} novos arquivos registrados.")
        return novos
    finally:
        con.close()


def criar_pendencia(numero: str, path_ogg: str, artista: str, musica: str) -> None:
    """
    Salva (ou substitui) uma pendência de confirmação de música para o número.
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("""
                INSERT INTO dim_pendencias
                    (numero, path_ogg, artista_original, musica_original, timestamp_criacao)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (numero) DO UPDATE SET
                    path_ogg          = EXCLUDED.path_ogg,
                    artista_original  = EXCLUDED.artista_original,
                    musica_original   = EXCLUDED.musica_original,
                    timestamp_criacao = EXCLUDED.timestamp_criacao
            """, [numero, path_ogg, artista, musica, datetime.now()])
        con.commit()
        print(f"[DB] Pendência criada para {numero}: '{musica}' - '{artista}'")
    finally:
        con.close()


def buscar_pendencia(numero: str) -> dict | None:
    """
    Retorna a pendência ativa de um número, ou None se não houver ou tiver expirado.
    Pendências expiram após 30 minutos.
    """
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT path_ogg, artista_original, musica_original, timestamp_criacao "
                "FROM dim_pendencias WHERE numero = %s", [numero]
            )
            row = cur.fetchone()
        if not row:
            return None

        path_ogg, artista, musica, ts = row
        if datetime.now() - ts > timedelta(minutes=30):
            with con.cursor() as cur:
                cur.execute("DELETE FROM dim_pendencias WHERE numero = %s", [numero])
            con.commit()
            if os.path.isfile(path_ogg):
                os.remove(path_ogg)
            print(f"[DB] Pendência expirada para {numero} — .ogg removido.")
            return None

        return {"path_ogg": path_ogg, "artista_original": artista, "musica_original": musica}
    finally:
        con.close()


def remover_pendencia(numero: str) -> None:
    """Remove a pendência de um número sem deletar o .ogg."""
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("DELETE FROM dim_pendencias WHERE numero = %s", [numero])
        con.commit()
    finally:
        con.close()


def listar_acervo() -> list[dict]:
    """Retorna todos os registros do acervo como lista de dicionários."""
    con = _get_connection()
    try:
        with con.cursor() as cur:
            cur.execute("""
                SELECT id, artista, musica, file_path, data_inclusao
                FROM dim_musicas
                ORDER BY data_inclusao DESC;
            """)
            rows = cur.fetchall()

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

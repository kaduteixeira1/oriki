"""Erros da API sempre no formato {"erro": "<codigo>", "detalhes": {...}} (seção 8.1)."""
from flask import current_app, jsonify, request
from werkzeug.exceptions import HTTPException, InternalServerError

CODIGOS_PADRAO = {
    400: "corpo_invalido",
    401: "nao_autenticado",
    403: "sem_permissao",
    404: "nao_encontrado",
    405: "metodo_nao_permitido",
    413: "corpo_muito_grande",
    415: "tipo_de_conteudo_invalido",
    422: "regra_violada",
    429: "limite_de_tentativas",
    500: "erro_interno",
}


class ErroApi(Exception):
    def __init__(self, status: int, erro: str | None = None, **detalhes):
        super().__init__(erro)
        self.status = status
        self.erro = erro or CODIGOS_PADRAO.get(status, "erro")
        self.detalhes = detalhes


def resposta_erro(status: int, erro: str, detalhes: dict | None = None):
    corpo = {"erro": erro}
    if detalhes:
        corpo["detalhes"] = detalhes
    return jsonify(corpo), status


def _e_api() -> bool:
    return request.path == "/api" or request.path.startswith("/api/")


def registrar_erros(app) -> None:
    @app.errorhandler(ErroApi)
    def _erro_api(erro: ErroApi):
        return resposta_erro(erro.status, erro.erro, erro.detalhes)

    @app.errorhandler(HTTPException)
    def _erro_http(erro: HTTPException):
        if erro.code == 429:
            from .seguranca import log_seguranca
            log_seguranca("limite_excedido", rota=request.path)
        if not _e_api():
            return erro
        resposta, status = resposta_erro(erro.code or 500, CODIGOS_PADRAO.get(erro.code, "erro"))
        for nome, valor in erro.get_headers():
            if nome in ("Allow", "Retry-After"):  # ex.: Allow no 405
                resposta.headers[nome] = valor
        return resposta, status

    @app.errorhandler(InternalServerError)
    def _erro_interno(erro: InternalServerError):
        original = getattr(erro, "original_exception", None)
        if original is not None:
            current_app.logger.exception("Erro não tratado em %s %s", request.method, request.path,
                                         exc_info=original)
        if not _e_api():
            return erro
        # Nunca devolve detalhes internos (pilha, SQL) para o cliente.
        return resposta_erro(500, "erro_interno")

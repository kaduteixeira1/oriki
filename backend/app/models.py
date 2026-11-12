"""Tabelas do DER (seção 6). As regras de integridade também vivem no banco (CHECK), não só na API."""
import enum
import secrets
from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import (CHAR, BigInteger, Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer,
                        Numeric, SmallInteger, String, Text, UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import regras
from .extensoes import db


class PerfilUsuario(enum.StrEnum):
    BATEDOR = "batedor"
    FISCAL = "fiscal"
    ADMIN = "admin"


class StatusLote(enum.StrEnum):
    INCOMPLETO = "incompleto"
    COMPLETO = "completo"


class StatusCiclo(enum.StrEnum):
    APROVADO = "aprovado"
    REPROVADO = "reprovado"


def _enum(classe, nome):
    return Enum(classe, name=nome, values_callable=lambda e: [m.value for m in e], validate_strings=True)


def _agora():
    return regras.agora()


def _criado_em():
    return mapped_column(DateTime(timezone=True), nullable=False, default=_agora, server_default=func.now())


def _atualizado_em():
    return mapped_column(DateTime(timezone=True), nullable=False, default=_agora, onupdate=_agora,
                         server_default=func.now())


class Estabelecimento(db.Model):
    __tablename__ = "estabelecimentos"
    __table_args__ = (
        CheckConstraint(r"slug_qr ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_formato"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    endereco: Mapped[str] = mapped_column(String(255))
    licenca_numero: Mapped[str] = mapped_column(String(40), unique=True)
    licenca_validade: Mapped[date] = mapped_column(Date)
    curso_casa_acai_em: Mapped[date | None] = mapped_column(Date)
    slug_qr: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = _criado_em()
    updated_at: Mapped[datetime] = _atualizado_em()

    dispositivos: Mapped[list["Dispositivo"]] = relationship(back_populates="estabelecimento")


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_minusculo"),
        # Batedor exige estabelecimento; fiscal e admin não têm (seção 6.2).
        CheckConstraint("(perfil = 'batedor') = (estabelecimento_id IS NOT NULL)", name="perfil_estabelecimento"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[PerfilUsuario] = mapped_column(_enum(PerfilUsuario, "perfil_usuario"))
    estabelecimento_id: Mapped[int | None] = mapped_column(ForeignKey("estabelecimentos.id"), index=True)
    termo_aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Muda ao anonimizar ou trocar a senha: invalida todas as sessões e cookies "lembrar" já emitidos.
    token_sessao: Mapped[str] = mapped_column(String(32), default=lambda: secrets.token_hex(16))
    anonimizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _criado_em()
    updated_at: Mapped[datetime] = _atualizado_em()

    estabelecimento: Mapped[Estabelecimento | None] = relationship()

    def get_id(self) -> str:
        return f"{self.id}:{self.token_sessao}"

    @property
    def is_active(self) -> bool:
        return self.anonimizado_em is None

    def renovar_token_sessao(self) -> None:
        self.token_sessao = secrets.token_hex(16)


class Dispositivo(db.Model):
    __tablename__ = "dispositivos"
    __table_args__ = (
        CheckConstraint("identificador ~ '^[A-Z0-9]{3,20}$'", name="identificador_formato"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estabelecimento_id: Mapped[int] = mapped_column(ForeignKey("estabelecimentos.id"), index=True)
    identificador: Mapped[str] = mapped_column(String(20), unique=True)
    chave_hmac_cifrada: Mapped[str] = mapped_column(Text)
    ultimo_contato: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _criado_em()
    updated_at: Mapped[datetime] = _atualizado_em()

    estabelecimento: Mapped[Estabelecimento] = relationship(back_populates="dispositivos")


class Lote(db.Model):
    __tablename__ = "lotes"
    __table_args__ = (
        CheckConstraint("quantidade_rasas > 0", name="quantidade_positiva"),
        # O status nunca contradiz os dados (seção 8.4, PATCH).
        CheckConstraint("(status = 'completo') = (origem_fruto IS NOT NULL AND quantidade_rasas IS NOT NULL)",
                        name="status_coerente"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    origem_fruto: Mapped[str | None] = mapped_column(String(150))
    quantidade_rasas: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    catacao: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sanitizacao: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    resfriamento: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    status: Mapped[StatusLote] = mapped_column(_enum(StatusLote, "status_lote"), default=StatusLote.INCOMPLETO,
                                              server_default=StatusLote.INCOMPLETO.value)
    created_at: Mapped[datetime] = _criado_em()
    updated_at: Mapped[datetime] = _atualizado_em()

    dispositivo: Mapped[Dispositivo] = relationship()
    ciclo: Mapped["Ciclo"] = relationship(back_populates="lote", uselist=False)


class Ciclo(db.Model):
    """Prova do branqueamento. Imutável: um gatilho no banco recusa UPDATE e DELETE (migração inicial)."""
    __tablename__ = "ciclos"
    __table_args__ = (
        CheckConstraint("fim >= inicio", name="fim_depois_inicio"),
        CheckConstraint("temp_min <= temp_max", name="temp_ordem"),
        CheckConstraint("temp_min >= -55 AND temp_max <= 125", name="temp_faixa"),
        CheckConstraint("segundos_acima_80 >= 0", name="segundos_positivos"),
        CheckConstraint("contador >= 1", name="contador_positivo"),
        CheckConstraint("status = 'reprovado' OR segundos_acima_80 >= 10", name="aprovado_coerente"),
        CheckConstraint("assinatura ~ '^[0-9a-f]{64}$'", name="assinatura_formato"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), unique=True)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fim: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temp_min: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    temp_max: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    segundos_acima_80: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[StatusCiclo] = mapped_column(_enum(StatusCiclo, "status_ciclo"))
    contador: Mapped[int] = mapped_column(Integer)
    assinatura: Mapped[str] = mapped_column(CHAR(64))
    relogio_divergente: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = _criado_em()

    lote: Mapped[Lote] = relationship(back_populates="ciclo")


class Vistoria(db.Model):
    __tablename__ = "vistorias"
    __table_args__ = (
        Index("ix_vistorias_estabelecimento_data", "estabelecimento_id", text("data DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estabelecimento_id: Mapped[int] = mapped_column(ForeignKey("estabelecimentos.id"))
    fiscal_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data: Mapped[date] = mapped_column(Date)
    resultado: Mapped[str] = mapped_column(String(40))
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _criado_em()
    updated_at: Mapped[datetime] = _atualizado_em()

    fiscal: Mapped[Usuario] = relationship()


class AcessoQR(db.Model):
    """Total de acessos vindos do QR por dia. Não guarda IP nem nada do visitante (LGPD)."""
    __tablename__ = "acessos_qr"
    __table_args__ = (
        UniqueConstraint("estabelecimento_id", "data", name="uq_acessos_qr_estabelecimento_data"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    estabelecimento_id: Mapped[int] = mapped_column(ForeignKey("estabelecimentos.id"))
    data: Mapped[date] = mapped_column(Date)
    total: Mapped[int] = mapped_column(Integer, default=0)


class RecusaEnvio(db.Model):
    """OR-31: ciclo recusado no POST /api/ciclos (assinatura, conflito, formato…), para o painel do fiscal.

    Só é gravada depois que a assinatura do envio confere: quem não tem a chave do dispositivo não
    consegue encher esta tabela.
    """
    __tablename__ = "recusas_envio"
    __table_args__ = (Index("ix_recusas_envio_dispositivo_criado", "dispositivo_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"))
    codigo: Mapped[str | None] = mapped_column(String(40))
    motivo: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = _criado_em()

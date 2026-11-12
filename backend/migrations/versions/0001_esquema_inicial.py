"""esquema inicial: tabelas do DER (seção 6), enums, CHECKs, índices e ciclos imutáveis

Revision ID: 0001
Revises: 
Create Date: 2026-10-08 15:14:41.064406

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('estabelecimentos',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('nome', sa.String(length=150), nullable=False),
    sa.Column('endereco', sa.String(length=255), nullable=False),
    sa.Column('licenca_numero', sa.String(length=40), nullable=False),
    sa.Column('licenca_validade', sa.Date(), nullable=False),
    sa.Column('curso_casa_acai_em', sa.Date(), nullable=True),
    sa.Column('slug_qr', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("slug_qr ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_estabelecimentos_slug_formato')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_estabelecimentos')),
    sa.UniqueConstraint('licenca_numero', name=op.f('uq_estabelecimentos_licenca_numero')),
    sa.UniqueConstraint('slug_qr', name=op.f('uq_estabelecimentos_slug_qr'))
    )
    op.create_table('acessos_qr',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('estabelecimento_id', sa.BigInteger(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['estabelecimento_id'], ['estabelecimentos.id'], name=op.f('fk_acessos_qr_estabelecimento_id_estabelecimentos')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acessos_qr')),
    sa.UniqueConstraint('estabelecimento_id', 'data', name='uq_acessos_qr_estabelecimento_data')
    )
    op.create_table('dispositivos',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('estabelecimento_id', sa.BigInteger(), nullable=False),
    sa.Column('identificador', sa.String(length=20), nullable=False),
    sa.Column('chave_hmac_cifrada', sa.Text(), nullable=False),
    sa.Column('ultimo_contato', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("identificador ~ '^[A-Z0-9]{3,20}$'", name=op.f('ck_dispositivos_identificador_formato')),
    sa.ForeignKeyConstraint(['estabelecimento_id'], ['estabelecimentos.id'], name=op.f('fk_dispositivos_estabelecimento_id_estabelecimentos')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dispositivos')),
    sa.UniqueConstraint('identificador', name=op.f('uq_dispositivos_identificador'))
    )
    with op.batch_alter_table('dispositivos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dispositivos_estabelecimento_id'), ['estabelecimento_id'], unique=False)

    op.create_table('usuarios',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=150), nullable=False),
    sa.Column('senha_hash', sa.String(length=255), nullable=False),
    sa.Column('perfil', sa.Enum('batedor', 'fiscal', 'admin', name='perfil_usuario'), nullable=False),
    sa.Column('estabelecimento_id', sa.BigInteger(), nullable=True),
    sa.Column('termo_aceito_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_sessao', sa.String(length=32), nullable=False),
    sa.Column('anonimizado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(perfil = 'batedor') = (estabelecimento_id IS NOT NULL)", name=op.f('ck_usuarios_perfil_estabelecimento')),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_usuarios_email_minusculo')),
    sa.ForeignKeyConstraint(['estabelecimento_id'], ['estabelecimentos.id'], name=op.f('fk_usuarios_estabelecimento_id_estabelecimentos')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usuarios')),
    sa.UniqueConstraint('email', name=op.f('uq_usuarios_email'))
    )
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuarios_estabelecimento_id'), ['estabelecimento_id'], unique=False)

    op.create_table('lotes',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('dispositivo_id', sa.BigInteger(), nullable=False),
    sa.Column('codigo', sa.String(length=40), nullable=False),
    sa.Column('origem_fruto', sa.String(length=150), nullable=True),
    sa.Column('quantidade_rasas', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('catacao', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('sanitizacao', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('resfriamento', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.Enum('incompleto', 'completo', name='status_lote'), server_default='incompleto', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'completo') = (origem_fruto IS NOT NULL AND quantidade_rasas IS NOT NULL)", name=op.f('ck_lotes_status_coerente')),
    sa.CheckConstraint('quantidade_rasas > 0', name=op.f('ck_lotes_quantidade_positiva')),
    sa.ForeignKeyConstraint(['dispositivo_id'], ['dispositivos.id'], name=op.f('fk_lotes_dispositivo_id_dispositivos')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lotes')),
    sa.UniqueConstraint('codigo', name=op.f('uq_lotes_codigo'))
    )
    with op.batch_alter_table('lotes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lotes_dispositivo_id'), ['dispositivo_id'], unique=False)

    op.create_table('vistorias',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('estabelecimento_id', sa.BigInteger(), nullable=False),
    sa.Column('fiscal_id', sa.BigInteger(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('resultado', sa.String(length=40), nullable=False),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['estabelecimento_id'], ['estabelecimentos.id'], name=op.f('fk_vistorias_estabelecimento_id_estabelecimentos')),
    sa.ForeignKeyConstraint(['fiscal_id'], ['usuarios.id'], name=op.f('fk_vistorias_fiscal_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vistorias'))
    )
    with op.batch_alter_table('vistorias', schema=None) as batch_op:
        batch_op.create_index('ix_vistorias_estabelecimento_data', ['estabelecimento_id', sa.literal_column('data DESC')], unique=False)
        batch_op.create_index(batch_op.f('ix_vistorias_fiscal_id'), ['fiscal_id'], unique=False)

    op.create_table('ciclos',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('inicio', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fim', sa.DateTime(timezone=True), nullable=False),
    sa.Column('temp_min', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('temp_max', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('segundos_acima_80', sa.SmallInteger(), nullable=False),
    sa.Column('status', sa.Enum('aprovado', 'reprovado', name='status_ciclo'), nullable=False),
    sa.Column('contador', sa.Integer(), nullable=False),
    sa.Column('assinatura', sa.CHAR(length=64), nullable=False),
    sa.Column('relogio_divergente', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("assinatura ~ '^[0-9a-f]{64}$'", name=op.f('ck_ciclos_assinatura_formato')),
    sa.CheckConstraint("status = 'reprovado' OR segundos_acima_80 >= 10", name=op.f('ck_ciclos_aprovado_coerente')),
    sa.CheckConstraint('contador >= 1', name=op.f('ck_ciclos_contador_positivo')),
    sa.CheckConstraint('fim >= inicio', name=op.f('ck_ciclos_fim_depois_inicio')),
    sa.CheckConstraint('segundos_acima_80 >= 0', name=op.f('ck_ciclos_segundos_positivos')),
    sa.CheckConstraint('temp_min <= temp_max', name=op.f('ck_ciclos_temp_ordem')),
    sa.CheckConstraint('temp_min >= -55 AND temp_max <= 125', name=op.f('ck_ciclos_temp_faixa')),
    sa.ForeignKeyConstraint(['lote_id'], ['lotes.id'], name=op.f('fk_ciclos_lote_id_lotes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ciclos')),
    sa.UniqueConstraint('lote_id', name=op.f('uq_ciclos_lote_id'))
    )
    with op.batch_alter_table('ciclos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ciclos_inicio'), ['inicio'], unique=False)


    # Ciclo é prova: nenhum UPDATE ou DELETE, nem por bug da API nem por acesso direto ao banco.
    op.execute("""
        CREATE FUNCTION ciclos_imutaveis() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ciclos são imutáveis (registro sanitário)';
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER ciclos_sem_alteracao BEFORE UPDATE OR DELETE ON ciclos
        FOR EACH ROW EXECUTE FUNCTION ciclos_imutaveis()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS ciclos_sem_alteracao ON ciclos")
    op.execute("DROP FUNCTION IF EXISTS ciclos_imutaveis()")
    with op.batch_alter_table('ciclos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ciclos_inicio'))

    op.drop_table('ciclos')
    with op.batch_alter_table('vistorias', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vistorias_fiscal_id'))
        batch_op.drop_index('ix_vistorias_estabelecimento_data')

    op.drop_table('vistorias')
    with op.batch_alter_table('lotes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lotes_dispositivo_id'))

    op.drop_table('lotes')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuarios_estabelecimento_id'))

    op.drop_table('usuarios')
    with op.batch_alter_table('dispositivos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dispositivos_estabelecimento_id'))

    op.drop_table('dispositivos')
    op.drop_table('acessos_qr')
    op.drop_table('estabelecimentos')
    for nome in ("status_ciclo", "status_lote", "perfil_usuario"):
        sa.Enum(name=nome).drop(op.get_bind(), checkfirst=True)

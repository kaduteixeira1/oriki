"""recusas de envio (OR-31): ciclos recusados no POST /api/ciclos, para o painel do fiscal

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 23:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('recusas_envio',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('dispositivo_id', sa.BigInteger(), nullable=False),
    sa.Column('codigo', sa.String(length=40), nullable=True),
    sa.Column('motivo', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dispositivo_id'], ['dispositivos.id'], name=op.f('fk_recusas_envio_dispositivo_id_dispositivos')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recusas_envio'))
    )
    op.create_index('ix_recusas_envio_dispositivo_criado', 'recusas_envio', ['dispositivo_id', 'created_at'])


def downgrade():
    op.drop_index('ix_recusas_envio_dispositivo_criado', table_name='recusas_envio')
    op.drop_table('recusas_envio')

"""initial schema

Revision ID: d99e6f1429b5
Revises:
Create Date: 2026-03-03 19:04:06.400021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd99e6f1429b5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pipelines table
    op.create_table(
        'pipelines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('entry_url', sa.Text(), nullable=False),
        sa.Column('use_google_search', sa.Boolean(), server_default='false'),
        sa.Column('google_search_term', sa.String(200), nullable=True),
        sa.Column('onboarding_steps', postgresql.JSON(), nullable=True),
        sa.Column('input_selector', sa.Text(), nullable=False),
        sa.Column('submit_method', sa.String(20), server_default='enter_key'),
        sa.Column('submit_selector', sa.Text(), nullable=True),
        sa.Column('capture_method', sa.String(20), server_default='websocket'),
        sa.Column('ws_url_pattern', sa.Text(), nullable=True),
        sa.Column('ws_decode_base64', sa.Boolean(), server_default='false'),
        sa.Column('ws_ignore_pattern', sa.Text(), nullable=True),
        sa.Column('ws_completion_signal', sa.Text(), nullable=True),
        sa.Column('dom_response_selector', sa.Text(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # scrape_tasks table
    op.create_table(
        'scrape_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('country', sa.String(5), server_default='US'),
        sa.Column('status', sa.Enum('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', name='taskstatus'), server_default='QUEUED'),
        sa.Column('pipeline_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('instance_id', sa.String(50), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('response_sources', postgresql.JSON(), nullable=True),
        sa.Column('response_markdown', sa.Text(), nullable=True),
        sa.Column('response_raw', postgresql.JSON(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('failure_step', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # instance_logs table
    op.create_table(
        'instance_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instance_id', sa.String(50), nullable=False, index=True),
        sa.Column('level', sa.String(10), server_default='INFO'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('step', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('instance_logs')
    op.drop_table('scrape_tasks')
    op.drop_table('pipelines')
    op.execute('DROP TYPE IF EXISTS taskstatus')

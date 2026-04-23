from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.privacy import hash_guild

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.db.repositories import GuildSettingsRepository
    from bot.voice import GuildVoiceStateManager


type SettingKey = Literal['idle_timeout', 'skip_votes', 'volume', 'locale']


class SettingsCog(commands.Cog):
    """`/settings` command group — per-guild overrides for playback defaults.

    Settings persist in SQLite so the bot no longer loses state on
    restart — replaces the `--force-recreate` workaround that was
    nuking in-memory config nightly.
    """

    group = app_commands.Group(
        name='settings',
        description='Per-guild playback settings.',
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    def __init__(
        self,
        bot: commands.Bot,
        *,
        settings: Settings,
        repo: GuildSettingsRepository,
        voice_states: GuildVoiceStateManager,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.repo = repo
        self.voice_states = voice_states

    def _guild_hash(self, guild_id: int) -> str:
        secret = self.settings.require_pii_hash_key().get_secret_value()
        return hash_guild(guild_id, secret=secret)

    @group.command(name='view', description="Show this guild's settings.")
    async def view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None  # guild_only=True above
        row = await self.repo.get(self._guild_hash(interaction.guild_id))
        defaults = self.settings

        idle = row.idle_timeout_seconds if row else None
        skip = row.skip_vote_threshold if row else None
        vol_pct = row.default_volume_pct if row else None
        locale = row.locale if row else None

        default_idle = f'{defaults.idle_timeout_seconds}s (default)'
        default_skip = f'{defaults.skip_vote_threshold} (default)'
        default_vol = f'{int(defaults.default_volume * 100)}% (default)'
        lines = [
            f'**idle_timeout**: {_render(idle, default_idle, suffix="s")}',
            f'**skip_votes**: {_render(skip, default_skip)}',
            f'**volume**: {_render(vol_pct, default_vol, suffix="%")}',
            f'**locale**: {_render(locale, "(default)")}',
        ]
        embed = discord.Embed(
            title='Guild settings',
            description='\n'.join(lines),
            color=discord.Color.blurple(),
        ).set_footer(
            text='Use /settings set to override, /settings reset to clear.',
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(
        name='set', description='Override a playback setting for this guild.'
    )
    @app_commands.describe(
        key='Which setting to change.',
        value=(
            'New value. idle_timeout: 10-3600 (seconds). '
            'skip_votes: 1-20. volume: 0-100. locale: 2-8 chars.'
        ),
    )
    async def set_(
        self,
        interaction: discord.Interaction,
        key: SettingKey,
        value: str,
    ) -> None:
        assert interaction.guild_id is not None
        update = _parse_update(key, value)
        await self.repo.upsert(
            self._guild_hash(interaction.guild_id), **update
        )
        self.voice_states.invalidate(interaction.guild_id)
        await interaction.response.send_message(
            f'Set **{key}** to **{value}**. '
            'The change applies the next time /mi is used here.',
            ephemeral=True,
        )

    @group.command(
        name='reset', description='Drop all overrides for this guild.'
    )
    async def reset(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        await self.repo.delete(self._guild_hash(interaction.guild_id))
        self.voice_states.invalidate(interaction.guild_id)
        await interaction.response.send_message(
            'Guild settings reset to defaults.', ephemeral=True
        )


def _render(
    value: int | str | None,
    default: str,
    *,
    suffix: str = '',
) -> str:
    if value is None:
        return default
    return f'{value}{suffix}'


def _parse_update(key: SettingKey, raw: str) -> dict[str, int | str | None]:
    if key == 'idle_timeout':
        n = _int_in_range(raw, 10, 3600)
        return {'idle_timeout_seconds': n}
    if key == 'skip_votes':
        n = _int_in_range(raw, 1, 20)
        return {'skip_vote_threshold': n}
    if key == 'volume':
        n = _int_in_range(raw, 0, 100)
        return {'default_volume_pct': n}
    if key == 'locale':
        raw = raw.strip()
        if not 2 <= len(raw) <= 8:
            raise ValueError('locale must be 2-8 characters')
        return {'locale': raw}
    raise ValueError(f'unknown setting key: {key}')


def _int_in_range(raw: str, lo: int, hi: int) -> int:
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(f'value must be an integer, got {raw!r}') from exc
    if not lo <= n <= hi:
        raise ValueError(f'value must be in [{lo}, {hi}], got {n}')
    return n

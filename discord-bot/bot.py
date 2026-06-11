"""
PolyQuest Discord Bot — Publica patch notes em um canal específico.
Uso: /patchnote versão tipo notas
"""

import os
import discord
from discord import app_commands
from datetime import datetime

TOKEN = os.environ.get("POLYQUEST_BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("POLYQUEST_CHANNEL_ID", "0"))

TIPOS = {
    "release": {"emoji": "🚀", "cor": 0x4CAF50, "label": "Nova versão"},
    "hotfix": {"emoji": "🔧", "cor": 0xFF9800, "label": "Hotfix"},
    "beta": {"emoji": "🧪", "cor": 0x9C27B0, "label": "Beta"},
}


class PolyQuestBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = PolyQuestBot()


@bot.tree.command(name="patchnote", description="Publica um patch note no canal oficial")
@app_commands.describe(
    versao="Versão (ex: v1.3.1)",
    tipo="Tipo da atualização",
    notas="Notas da atualização (use \\n para quebrar linha)",
)
@app_commands.choices(tipo=[
    app_commands.Choice(name="Release — nova versão", value="release"),
    app_commands.Choice(name="Hotfix — correção", value="hotfix"),
    app_commands.Choice(name="Beta — versão de teste", value="beta"),
])
@app_commands.checks.has_permissions(manage_messages=True)
async def patchnote(
    interaction: discord.Interaction,
    versao: str,
    tipo: app_commands.Choice[str],
    notas: str,
):
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        await interaction.response.send_message(
            "❌ Canal de patch notes não encontrado. Verifique o POLYQUEST_CHANNEL_ID.",
            ephemeral=True,
        )
        return

    info = TIPOS[tipo.value]
    notas_formatadas = notas.replace("\\n", "\n")

    embed = discord.Embed(
        title=f"{info['emoji']}  PolyQuest — {info['label']} {versao}",
        description=notas_formatadas,
        color=info["cor"],
        timestamp=datetime.now(),
    )
    embed.set_footer(text="PolyQuest", icon_url="https://nakacode.github.io/PolyQuest/logo.png")
    embed.add_field(
        name="📥 Download",
        value="[Baixar PolyQuest](https://nakacode.github.io/PolyQuest/#download)",
        inline=False,
    )

    await channel.send(embed=embed)
    await interaction.response.send_message(
        f"✅ Patch note **{versao}** publicado em <#{CHANNEL_ID}>!",
        ephemeral=True,
    )


@patchnote.error
async def patchnote_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Você precisa da permissão **Gerenciar Mensagens** para usar este comando.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"❌ Erro: {error}",
            ephemeral=True,
        )


@bot.event
async def on_ready():
    print(f"[OK] {bot.user} online! ID: {bot.user.id}")
    print(f"[CH] Canal de patch notes: {CHANNEL_ID}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="PolyQuest updates",
        )
    )


if __name__ == "__main__":
    if not TOKEN:
        print("[ERRO] Defina a variavel POLYQUEST_BOT_TOKEN")
        exit(1)
    if not CHANNEL_ID:
        print("[ERRO] Defina a variavel POLYQUEST_CHANNEL_ID")
        exit(1)
    bot.run(TOKEN)

import discord
from discord import app_commands
from discord.ext import commands
import datetime
import io
import re
import aiohttp
from typing import Optional, Tuple, List

# ==========================================
# ⚙️ إعدادات المتغيرات (ضع بياناتك هنا)
# ==========================================
TOKEN = "MTQ3MjA0NTY0ODAxNzYyNTE1Mg.GEoY_0.4BG0UakOVtd8AxpN-kzONFzQMvWoWMA1DCkjj4"
PC_CHANNEL_ID = 1472031752213233707          # قناة سكريبتات الكمبيوتر
MOBILE_CHANNEL_ID = 1472031348926582814     # قناة سكريبتات الموبايل
ADMIN_LOG_CHANNEL_ID = 1472231359203246284   # قناة مراجعة الإدارة
ADMIN_ROLE_ID = 1450957069938327813          # رتبة الإدارة المسؤولة

# إعدادات معالجة الملفات الثنائية
FILENAME_PATTERN = re.compile(r"^ProjectData_slot_(1[0-2]|[1-9])\.bytes$", re.IGNORECASE)
PATTERN_START = 0x38
PATTERN_END = 0x42

# ==========================================
# 🛠️ أدوات المنطق الثنائي (Varint Logic)
# ==========================================
def decode_varint(data: bytes, start: int) -> Tuple[int, int]:
    value, shift, pos = 0, 0, start
    while True:
        b = data[pos]
        value |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80): break
        shift += 7
    return value, pos - start

def encode_varint(num: int) -> bytes:
    if num == 0: return b"\x00"
    out = bytearray()
    while num:
        to_write = num & 0x7F
        num >>= 7
        if num: out.append(to_write | 0x80)
        else: out.append(to_write)
    return bytes(out)

def find_uid_in_binary(data: bytes) -> Optional[dict]:
    size = len(data)
    for i in range(size - 2):
        if data[i] == PATTERN_START:
            try:
                uid_val, uid_len = decode_varint(data, i + 1)
                if i + 1 + uid_len < size and data[i + 1 + uid_len] == PATTERN_END:
                    return {"offset": i + 1, "length": uid_len, "uid": uid_val}
            except: continue
    return None

# ==========================================
# 💎 واجهة محرر الـ UID المطورة
# ==========================================
class UIDUpdateModal(discord.ui.Modal, title="📝 تحديث معرف UID"):
    new_uid = discord.ui.TextInput(label="الـ UID الجديد", placeholder="أدخل الرقم الجديد هنا...", min_length=1)

    def __init__(self, file_bytes, filename, info):
        super().__init__()
        self.file_bytes = file_bytes
        self.filename = filename
        self.info = info

    async def on_submit(self, interaction: discord.Interaction):
        if not self.new_uid.value.isdigit():
            return await interaction.response.send_message("❌ خطأ: يرجى إدخال أرقام فقط.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            new_val = int(self.new_uid.value)
            new_var_bytes = encode_varint(new_val)
            modified_data = (self.file_bytes[:self.info["offset"]] + new_var_bytes + self.file_bytes[self.info["offset"] + self.info["length"]:])

            file_out = io.BytesIO(modified_data)
            discord_file = discord.File(file_out, filename=self.filename)
            
            embed = discord.Embed(title="✅ تم التعديل بنجاح", color=discord.Color.green())
            embed.add_field(name="📂 الملف", value=f"`{self.filename}`")
            embed.add_field(name="🔢 UID الجديد", value=f"`{new_val}`")

            try:
                await interaction.user.send(embed=embed, file=discord_file)
                await interaction.followup.send("🚀 تم إرسال الملف المعدل لرسائلك الخاصة!", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("⚠️ فشل الإرسال! تأكد من فتح الرسائل الخاصة (DM) ثم حاول مجدداً.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"🧨 خطأ تقني: {e}", ephemeral=True)

class UIDEditorView(discord.ui.View):
    def __init__(self, data, filename, info):
        super().__init__(timeout=120)
        self.data, self.filename, self.info = data, filename, info

    @discord.ui.button(label="تعديل المعرف", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UIDUpdateModal(self.data, self.filename, self.info))

# ==========================================
# 📝 نظام السكريبتات والمراجعة
# ==========================================
class AdminReviewView(discord.ui.View):
    def __init__(self, author, platform, name, desc, attachments):
        super().__init__(timeout=None)
        self.author, self.platform, self.name, self.desc, self.attachments = author, platform, name, desc, attachments

    @discord.ui.button(label="قبول ✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles):
            return await interaction.response.send_message("عذراً، هذا الزر للإدارة فقط.", ephemeral=True)

        target_id = PC_CHANNEL_ID if self.platform == "PC" else MOBILE_CHANNEL_ID
        channel = interaction.guild.get_channel(target_id)
        color = discord.Color.blue() if self.platform == "PC" else discord.Color.orange()

        embed = discord.Embed(title=f"🚀 {self.name}", description=f"**الوصف:**\n{self.desc}", color=color, timestamp=datetime.datetime.now())
        embed.set_author(name=f"بواسطة: {self.author.display_name}", icon_url=self.author.display_avatar.url)
        embed.set_footer(text=f"المنصة: {self.platform} Edition")
        
        if self.attachments: embed.set_image(url=self.attachments[0])

        main_msg = await channel.send(embed=embed)
        if len(self.attachments) > 1:
            for extra in self.attachments[1:]: await channel.send(extra, reference=main_msg)

        await interaction.message.delete()
        await interaction.response.send_message(f"تم نشر سكريبت {self.author.name} بنجاح!", ephemeral=True)

    @discord.ui.button(label="رفض ❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles):
            return await interaction.response.send_message("عذراً، هذا الزر للإدارة فقط.", ephemeral=True)
        await interaction.message.delete()
        await interaction.response.send_message("تم رفض الطلب وحذفه.", ephemeral=True)

class ScriptSubmissionModal(discord.ui.Modal, title="تفاصيل السكريبت الجديد"):
    s_name = discord.ui.TextInput(label="اسم السكريبت", placeholder="Auto-Farm V3...")
    s_desc = discord.ui.TextInput(label="الوصف أو الكود", style=discord.TextStyle.paragraph)

    def __init__(self, platform, files):
        super().__init__()
        self.platform, self.files = platform, files

    async def on_submit(self, interaction: discord.Interaction):
        admin_channel = interaction.guild.get_channel(ADMIN_LOG_CHANNEL_ID)
        embed = discord.Embed(title="🔍 مراجعة سكريبت", color=discord.Color.yellow())
        embed.add_field(name="الكاتب", value=interaction.user.mention)
        embed.add_field(name="المنصة", value=self.platform)
        embed.add_field(name="الاسم", value=self.s_name.value, inline=False)
        if self.files: embed.set_image(url=self.files[0])

        await admin_channel.send(embed=embed, view=AdminReviewView(interaction.user, self.platform, self.s_name.value, self.s_desc.value, self.files))
        await interaction.response.send_message("✅ تم إرسال طلبك للإدارة للمراجعة.", ephemeral=True)

# ==========================================
# 🤖 البوت الأساسي والأوامر
# ==========================================
class CraftyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Logged in as {self.user} | Commands Synced")

bot = CraftyBot()

@bot.tree.command(name="script", description="تقديم سكريبت مع دعم حتى 3 مرفقات")
@app_commands.choices(platform=[app_commands.Choice(name="PC Edition", value="PC"), app_commands.Choice(name="Mobile Edition", value="Mobile")])
async def script(interaction: discord.Interaction, platform: app_commands.Choice[str], file1: discord.Attachment, file2: Optional[discord.Attachment]=None, file3: Optional[discord.Attachment]=None):
    files = [f.url for f in [file1, file2, file3] if f]
    await interaction.response.send_modal(ScriptSubmissionModal(platform.value, files))

@bot.tree.command(name="edit_uid", description="محرر UID احترافي لملفات .bytes")
async def edit_uid(interaction: discord.Interaction, file: discord.Attachment):
    if not FILENAME_PATTERN.match(file.filename):
        return await interaction.response.send_message("❌ خطأ: اسم الملف يجب أن يكون `ProjectData_slot_X.bytes`", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    async with aiohttp.ClientSession() as session:
        async with session.get(file.url) as r: data = await r.read()

    info = find_uid_in_binary(data)
    if not info: return await interaction.followup.send("❌ فشل التحليل: لم يتم العثور على UID داخل الملف.")

    embed = discord.Embed(title="🛠️ محرر ملفات Craftland", description=f"تم العثور على معرف UID: `{info['uid']}`", color=discord.Color.purple())
    embed.set_footer(text="انقر على الزر لتعديل المعرف وإرساله لخاصك.")
    await interaction.followup.send(embed=embed, view=UIDEditorView(data, file.filename, info), ephemeral=True)

# --- أوامر الإدارة ---
@bot.tree.command(name="mute", description="إسكات عضو")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int):
    await member.timeout(datetime.timedelta(minutes=minutes))
    await interaction.response.send_message(f"🔇 تم إسكات {member.mention} لمدة {minutes} دقيقة.")

@bot.tree.command(name="unmute", description="فك الإسكات")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"🔊 تم فك الإسكات عن {member.mention}.")

@bot.tree.command(name="clear", description="مسح الرسائل")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"✅ تم مسح {amount} رسالة.", ephemeral=True)

@bot.tree.command(name="unban", description="فك حظر بالـ ID")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def unban(interaction: discord.Interaction, user_id: str):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user)
    await interaction.response.send_message(f"🔓 تم فك حظر {user.name}.")

bot.run(TOKEN)
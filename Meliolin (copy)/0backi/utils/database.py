import aiosqlite

class Database:
    def __init__(self, path):
        self.path = path
        self.conn = None

    async def setup(self):
        self.conn = await aiosqlite.connect(self.path)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS autoresponders (
                guild_id INTEGER NOT NULL,
                trigger TEXT NOT NULL,
                response TEXT NOT NULL,
                PRIMARY KEY (guild_id, trigger)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fake_perms (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                perm_name TEXT NOT NULL,
                PRIMARY KEY (guild_id, target_id, perm_name)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pingable_roles (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, target_id, role_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                threshold INTEGER NOT NULL DEFAULT 3,
                interval_seconds INTEGER NOT NULL DEFAULT 10
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                jail_role_id INTEGER,
                appeal_channel_id INTEGER
            )
        """)

        for column, coltype in [
            ("modlog_channel_id", "INTEGER"),
            ("booster_top_divider_id", "INTEGER"),
            ("booster_bottom_divider_id", "INTEGER"),
            ("prefix", "TEXT"),
        ]:
            try:
                await self.conn.execute(f"ALTER TABLE guild_config ADD COLUMN {column} {coltype}")
            except aiosqlite.OperationalError:
                pass

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS jail_appeals (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                has_pending_appeal INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mod_cases (
                guild_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                moderator_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (guild_id, case_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pingrole_cooldown_config (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                role_id INTEGER,
                cooldown_seconds INTEGER NOT NULL
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pingrole_last_used (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                last_used_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, role_id)
            )
        """)

        # Users granted no-prefix command access by the bot owner (global, not per-server).
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS noprefix_grants (
                user_id INTEGER PRIMARY KEY
            )
        """)

        # Users allowed to curse others with uwu (the ability), separate
        # from who is currently cursed (the effect).
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS uwu_permitted (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS uwu_cursed (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS eaten_roles (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, target_id, role_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS forced_nicknames (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                nickname TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS join_invites (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                inviter_id INTEGER,
                invite_code TEXT,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        await self.conn.commit()

    async def execute(self, query, params=()):
        await self.conn.execute(query, params)
        await self.conn.commit()

    async def fetchone(self, query, params=()):
        cursor = await self.conn.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetchall(self, query, params=()):
        cursor = await self.conn.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

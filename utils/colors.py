import discord

def parse_hex(hex_str: str):
    """Parse a hex color string like 'ff0000' or '#ff0000' into a discord.Colour. Returns None if invalid."""
    if hex_str is None:
        return None
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) != 6:
        return None
    try:
        value = int(hex_str, 16)
    except ValueError:
        return None
    return discord.Colour(value)

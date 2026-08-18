# Registry for phrase-triggered "commands" (things like replying "so tuff" or
# "let me eat your roles" instead of typing a real ~command). Cogs call
# register_trigger() once at import time; help systems read this list so
# these tricks never go undocumented again.

TEXT_TRIGGERS = []

def register_trigger(phrase: str, description: str, category: str = "Owner"):
    TEXT_TRIGGERS.append({"phrase": phrase, "description": description, "category": category})

def get_triggers_for(category: str):
    return [t for t in TEXT_TRIGGERS if t["category"] == category]

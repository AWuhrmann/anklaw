import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class VPSConfig:
    host: str = ""
    user: str = "ubuntu"
    ssh_key_path: str = "~/.ssh/id_rsa"
    db_path: str = "~/anki-agent/cards.db"
    script_path: str = "~/anki-agent"
    port: int = 22


@dataclass
class LocalConfig:
    anki_connect_url: str = "http://localhost:8765"


@dataclass
class GenerationConfig:
    cards_per_day: int = 20
    topic_instructions: str = ""
    deck_name: str = "AnkiAgent"
    card_type: str = "Basic"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-6"
    max_retries: int = 3
    research_enabled: bool = False


@dataclass
class Config:
    vps: VPSConfig = field(default_factory=VPSConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)


def load_config(config_path: Optional[str] = None) -> Config:
    if config_path is None:
        config_path = os.environ.get("ANKI_AGENT_CONFIG", "config.yaml")

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and fill in your settings."
        )

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    config = Config()

    if "vps" in data:
        v = data["vps"]
        config.vps = VPSConfig(
            host=v.get("host", ""),
            user=v.get("user", "ubuntu"),
            ssh_key_path=v.get("ssh_key_path", "~/.ssh/id_rsa"),
            db_path=v.get("db_path", "~/anki-agent/cards.db"),
            script_path=v.get("script_path", "~/anki-agent"),
            port=v.get("port", 22),
        )

    if "local" in data:
        l = data["local"]
        config.local = LocalConfig(
            anki_connect_url=l.get("anki_connect_url", "http://localhost:8765"),
        )

    if "generation" in data:
        g = data["generation"]
        config.generation = GenerationConfig(
            cards_per_day=g.get("cards_per_day", 20),
            topic_instructions=g.get("topic_instructions", ""),
            deck_name=g.get("deck_name", "AnkiAgent"),
            card_type=g.get("card_type", "Basic"),
            llm_provider=g.get("llm_provider", "anthropic"),
            llm_model=g.get("llm_model", "claude-opus-4-6"),
            max_retries=g.get("max_retries", 3),
            research_enabled=g.get("research_enabled", False),
        )

    return config

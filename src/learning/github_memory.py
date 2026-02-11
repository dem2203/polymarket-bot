"""
GitHub Memory Persistence — Railway Volumes yerine GitHub deposunu hafıza olarak kullanır.
Botun 'trade_history.json' dosyasını 'data-backup' branch'ine yedekler.
Her restart'ta bu branch'ten geri yükler.
"""

import os
import json
import logging
import base64
from typing import Optional
try:
    from github import Github, GithubException
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    class Github: pass
    class GithubException(Exception): pass
    print("⚠️ PyGithub bulunamadı, GitHub hafıza devre dışı.")

from src.config import settings
from src.learning.performance_tracker import HISTORY_FILE

logger = logging.getLogger("bot.learning.github")

BACKUP_BRANCH = "data-backup"

class GitHubMemory:
    """GitHub tabanlı hafıza yöneticisi."""

    def __init__(self):
        self.enabled = False
        if GITHUB_AVAILABLE:
            self.enabled = bool(settings.github_token and settings.github_repo)
        
        self.github = None
        self.repo = None
        
        if self.enabled:
            try:
                self.github = Github(settings.github_token)
                self.repo = self.github.get_repo(settings.github_repo)
                logger.info(f"✅ GitHub hafıza bağlantısı: {settings.github_repo}")
            except Exception as e:
                logger.error(f"GitHub bağlantı hatası: {e}")
                self.enabled = False

    def load_memory(self):
        """GitHub'dan trade geçmişini indir."""
        if not self.enabled:
            return

        try:
            contents = self.repo.get_contents("data/trade_history.json", ref=BACKUP_BRANCH)
            data = base64.b64decode(contents.content).decode("utf-8")
            
            # Yerel dosyaya yaz
            os.makedirs("data", exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                f.write(data)
            
            logger.info("📚 Hafıza GitHub'dan geri yüklendi.")
        except GithubException as e:
            if e.status == 404:
                logger.info("Hafıza dosyası henüz yok (yeni başlangıç).")
            else:
                logger.warning(f"GitHub hafıza yükleme hatası: {e}")
        except Exception as e:
            logger.error(f"Genel hafıza yükleme hatası: {e}")

    def save_memory(self):
        """Trade geçmişini GitHub'a yedekle."""
        if not self.enabled:
            return

        if not os.path.exists(HISTORY_FILE):
            return

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                content = f.read()

            # Backup branch var mı kontrol et
            try:
                self.repo.get_branch(BACKUP_BRANCH)
            except:
                # Yoksa oluştur (main'den)
                sb = self.repo.get_branch("main")
                self.repo.create_git_ref(ref=f"refs/heads/{BACKUP_BRANCH}", sha=sb.commit.sha)
                logger.info(f"Yedek branch '{BACKUP_BRANCH}' oluşturuldu.")

            # Dosya var mı kontrol et (update vs create)
            try:
                contents = self.repo.get_contents("data/trade_history.json", ref=BACKUP_BRANCH)
                self.repo.update_file(
                    path="data/trade_history.json",
                    message="🧠 Bot memory update [auto]",
                    content=content,
                    sha=contents.sha,
                    branch=BACKUP_BRANCH
                )
                logger.info("💾 Hafıza GitHub'a yedeklendi.")
            except GithubException as e:
                if e.status == 404:
                    self.repo.create_file(
                        path="data/trade_history.json",
                        message="🧠 Init bot memory [auto]",
                        content=content,
                        branch=BACKUP_BRANCH
                    )
                    logger.info("💾 Yeni hafıza dosyası GitHub'da oluşturuldu.")
                else:
                    raise e

        except Exception as e:
            logger.error(f"Hafıza yedekleme hatası: {e}")

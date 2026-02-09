"""Admin & Whitelist Access Control for Astra."""
import os


# --- ROOT ADMIN IDS (same as GemGem) ---
ADMIN_IDS = {
    69353483425292288,
    1365378902301741071,
    1324163881664253994,
    1225645079364894775,
}


class WhitelistManager:
    """File-backed whitelist for authorized users."""

    def __init__(self, filename="whitelist.txt"):
        self.filename = filename
        self.authorized_users = set()
        self._load()

    def _load(self):
        if not os.path.exists(self.filename):
            with open(self.filename, "w") as f:
                pass
        with open(self.filename, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.authorized_users.add(int(line))

    def _save(self):
        with open(self.filename, "w") as f:
            for uid in sorted(self.authorized_users):
                f.write(f"{uid}\n")

    def is_authorized(self, user_id):
        return user_id in ADMIN_IDS or user_id in self.authorized_users

    def add_user(self, user_id):
        self.authorized_users.add(user_id)
        self._save()

    def remove_user(self, user_id):
        if user_id in self.authorized_users:
            self.authorized_users.remove(user_id)
            self._save()
            return True
        return False

    def get_list(self):
        return list(self.authorized_users)


# Global instance
whitelist = WhitelistManager()

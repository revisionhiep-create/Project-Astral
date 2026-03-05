#!/bin/bash
# Apply DAVE decryption patch to discord-ext-voice-recv

READER_PY="/usr/local/lib/python3.11/site-packages/discord/ext/voice_recv/reader.py"

# Backup original
cp "$READER_PY" "$READER_PY.backup"

# Find the line with "packet.decrypted_data = self.decryptor.decrypt_rtp(packet)" and replace it
python3 << 'EOPYTHON'
import re

reader_py = "/usr/local/lib/python3.11/site-packages/discord/ext/voice_recv/reader.py"

with open(reader_py, "r") as f:
    content = f.read()

# Add import for davey at the top
if "import davey" not in content:
    # Find the last import statement and add after it
    import_pos = content.rfind("\nimport ")
    if import_pos == -1:
        import_pos = content.find("\n", content.find("from __future__"))
    next_newline = content.find("\n", import_pos + 1)
    content = content[:next_newline+1] + "import davey\n" + content[next_newline+1:]

# Find and replace the decryption line
old_code = "                packet.decrypted_data = self.decryptor.decrypt_rtp(packet)"

new_code = """                # First decrypt transport layer (RTP encryption)
                transport_decrypted = self.decryptor.decrypt_rtp(packet)

                # Then decrypt DAVE E2EE frame encryption if session exists
                if (hasattr(self.voice_client, '_connection') and
                    hasattr(self.voice_client._connection, 'dave_session') and
                    self.voice_client._connection.dave_session is not None):
                    try:
                        # Get Discord user ID from SSRC mapping
                        user_id = self.voice_client._get_id_from_ssrc(packet.ssrc)
                        if user_id is not None:
                            # DAVE decrypt(user_id, media_type, packet)
                            packet.decrypted_data = self.voice_client._connection.dave_session.decrypt(
                                user_id, davey.MediaType.audio, transport_decrypted
                            )
                        else:
                            # SSRC not mapped yet, fallback to transport-only
                            packet.decrypted_data = transport_decrypted
                    except Exception as e:
                        log.warning("DAVE decryption failed for SSRC %s: %s", packet.ssrc, e)
                        packet.decrypted_data = transport_decrypted  # Fallback to transport-only
                else:
                    packet.decrypted_data = transport_decrypted"""

content = content.replace(old_code, new_code)

with open(reader_py, "w") as f:
    f.write(content)

print("✅ DAVE decryption patch applied successfully")
EOPYTHON

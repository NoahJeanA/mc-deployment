#!/usr/bin/env python3
"""
Minecraft RCON-Konsole

Ein interaktives Kommandozeilen-Tool für die direkte Verwaltung
eines Minecraft-Servers über das RCON-Protokoll.

Verwendung:
python rcon.py --host <SERVER_IP> --port <RCON_PORT> --password <RCON_PASSWORD>
"""

import argparse
import sys
import os
import readline  # Für verbesserte Befehlszeileneingabe
import time

try:
    from mcrcon import MCRcon
except ImportError:
    print("Die mcrcon-Bibliothek ist nicht installiert.")
    print("Installieren Sie sie mit: pip install mcrcon")
    sys.exit(1)

def clear_screen():
    """Bildschirm löschen, funktioniert auf Windows und Unix-Systemen."""
    os.system('cls' if os.name == 'nt' else 'clear')

class MinecraftRCONConsole:
    def __init__(self, host, password, port=25575):
        self.host = host
        self.password = password
        self.port = port
        self.mcr = None
        self.connected = False
        self.command_history = []
        self.last_command_time = 0

    def connect(self):
        """Verbindung zum Minecraft-Server herstellen."""
        try:
            self.mcr = MCRcon(self.host, self.password, port=self.port)
            self.mcr.connect()
            self.connected = True
            return True
        except Exception as e:
            print(f"Fehler bei der Verbindung zum Server: {e}")
            return False

    def disconnect(self):
        """Verbindung zum Server trennen."""
        if self.connected and self.mcr:
            try:
                self.mcr.disconnect()
                print("Verbindung getrennt.")
            except Exception as e:
                print(f"Fehler beim Trennen der Verbindung: {e}")
            finally:
                self.connected = False

    def send_command(self, command):
        """Befehl an den Server senden und Antwort zurückgeben."""
        if not self.connected or not self.mcr:
            print("Nicht mit dem Server verbunden!")
            return None

        # Ratenbegrenzung für Befehle (um Serverüberlastung zu vermeiden)
        current_time = time.time()
        elapsed = current_time - self.last_command_time
        if elapsed < 0.5:  # Maximal 2 Befehle pro Sekunde
            time.sleep(0.5 - elapsed)

        try:
            response = self.mcr.command(command)
            self.command_history.append(command)
            self.last_command_time = time.time()
            return response
        except Exception as e:
            print(f"Fehler beim Senden des Befehls: {e}")
            return None

    def start_console(self):
        """Interaktive Konsole starten."""
        if not self.connect():
            print("Konnte keine Verbindung zum Server herstellen. Prüfen Sie Host, Port und Passwort.")
            return

        clear_screen()
        print("\n" + "=" * 60)
        print(" " * 20 + "MINECRAFT RCON KONSOLE")
        print("=" * 60)
        print(f"Verbunden mit: {self.host}:{self.port}")
        print("Geben Sie Befehle ein oder 'exit' zum Beenden.")
        print("Nützliche Befehle:")
        print("- help             : Zeigt verfügbare Befehle")
        print("- list             : Zeigt verbundene Spieler")
        print("- say <nachricht>  : Sendet Nachricht an alle Spieler")
        print("- op <spieler>     : Erteilt Operator-Status")
        print("- save-all         : Speichert die Weltdaten")
        print("- stop             : Fährt den Server herunter")
        print("- clear            : Löscht die Konsole")
        print("=" * 60 + "\n")

        # Erste Serverinformationen abrufen
        try:
            print("Serverinformationen:")
            version_info = self.send_command("version")
            if version_info:
                print(version_info)
            
            players = self.send_command("list")
            if players:
                print(players)
            print()
        except Exception as e:
            print(f"Fehler beim Abrufen der Serverinformationen: {e}")

        # Tab-Vervollständigung für häufige Befehle
        common_commands = [
            "help", "list", "say", "op", "deop", "kick", "ban", "pardon",
            "save-all", "save-off", "save-on", "stop", "clear", "weather", 
            "time set", "gamemode", "gamerule", "difficulty", "whitelist", "tp"
        ]
        
        def completer(text, state):
            options = [cmd for cmd in common_commands if cmd.startswith(text)]
            if state < len(options):
                return options[state]
            else:
                return None
                
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

        # Hauptschleife
        while self.connected:
            try:
                command = input("RCON> ").strip()
                
                if not command:
                    continue
                
                if command.lower() in ['exit', 'quit', 'bye']:
                    break
                
                if command.lower() == 'clear':
                    clear_screen()
                    continue
                
                response = self.send_command(command)
                if response:
                    print(response)
                
            except KeyboardInterrupt:
                print("\nBeenden...")
                break
            except Exception as e:
                print(f"Fehler: {e}")
                break

        self.disconnect()

def main():
    parser = argparse.ArgumentParser(description='Minecraft RCON Konsole')
    parser.add_argument('--host', default='localhost', help='RCON-Host (Standard: localhost)')
    parser.add_argument('--port', type=int, default=25575, help='RCON-Port (Standard: 25575)')
    parser.add_argument('--password', required=True, help='RCON-Passwort')
    
    args = parser.parse_args()
    
    console = MinecraftRCONConsole(args.host, args.password, args.port)
    console.start_console()

if __name__ == "__main__":
    main()
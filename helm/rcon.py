#!/usr/bin/env python3
# minecraft_rcon_console.py
# Eine interaktive Konsole für die Verwaltung von Minecraft-Servern über RCON

import argparse
import sys
import os
import readline  # Für verbesserte Befehlszeileneingabe

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

        try:
            response = self.mcr.command(command)
            self.command_history.append(command)
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
        print("\n" + "=" * 50)
        print("Minecraft RCON Konsole")
        print("=" * 50)
        print(f"Verbunden mit: {self.host}:{self.port}")
        print("Geben Sie Befehle ein oder 'exit' zum Beenden.")
        print("Nützliche Befehle: 'help', 'list', 'say <nachricht>', 'op <spieler>'")
        print("=" * 50 + "\n")

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

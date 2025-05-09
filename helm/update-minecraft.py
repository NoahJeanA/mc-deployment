#!/usr/bin/env python3
"""
Minecraft Zero-Downtime Update Script

Dieses Skript führt ein Update eines in Kubernetes laufenden Minecraft-Servers durch,
mit dem Ziel, die Ausfallzeit für Spieler zu minimieren. Es nutzt einen BungeeCord-Proxy,
um Spieler zwischen Servern umzuleiten, und synchronisiert Weltdaten für Konsistenz.

Voraussetzungen:
- kubectl muss im Pfad sein und konfiguriert sein, um auf den K8s-Cluster zuzugreifen
- helm muss im Pfad sein
- Python 3.6+
- mcrcon Bibliothek (pip install mcrcon)
- colorama (pip install colorama)
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    import mcrcon
    from colorama import Fore, Style, init
    init()  # Colorama initialisieren
except ImportError as e:
    print(f"Erforderliche Bibliothek fehlt: {e}")
    print("Bitte installieren Sie fehlende Abhängigkeiten mit: pip install mcrcon colorama")
    sys.exit(1)

# Konfiguration der Logging-Einstellungen
LOG_DIRECTORY = Path("logs")
LOG_DIRECTORY.mkdir(exist_ok=True)
LOG_FILENAME = f"minecraft_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_PATH = LOG_DIRECTORY / LOG_FILENAME

# Logger-Konfiguration
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("minecraft-updater")

# ANSI-Farbcodes für bessere Lesbarkeit im Terminal
class Colors:
    INFO = Fore.CYAN
    SUCCESS = Fore.GREEN
    WARNING = Fore.YELLOW
    ERROR = Fore.RED
    RESET = Style.RESET_ALL

def log(message, level="info", console_only=False):
    """
    Protokolliert eine Nachricht mit dem angegebenen Level und optionaler Konsolenformatierung.
    
    Args:
        message: Die zu protokollierende Nachricht
        level: Das Logging-Level (info, warning, error, success, debug)
        console_only: Wenn True, wird nur auf der Konsole ausgegeben, nicht in der Logdatei
    """
    color = Colors.RESET
    if level == "info":
        color = Colors.INFO
        if not console_only:
            logger.info(message)
    elif level == "warning":
        color = Colors.WARNING
        if not console_only:
            logger.warning(message)
    elif level == "error":
        color = Colors.ERROR
        if not console_only:
            logger.error(message)
    elif level == "success":
        color = Colors.SUCCESS
        if not console_only:
            logger.info(f"SUCCESS: {message}")
    elif level == "debug":
        if not console_only:
            logger.debug(message)
        else:
            print(f"DEBUG: {message}")
            return
    
    print(f"{color}{message}{Colors.RESET}")

def run_command(command, check=True, shell=False, capture_output=True):
    """
    Führt einen Shell-Befehl aus und protokolliert Ausgabe.
    
    Args:
        command: Der auszuführende Befehl (Liste oder String)
        check: Wenn True, wird bei Fehler eine Exception ausgelöst
        shell: Wenn True, wird der Befehl in einer Shell ausgeführt
        capture_output: Wenn True, wird die Ausgabe zurückgegeben
        
    Returns:
        Ein CompletedProcess-Objekt mit stdout und stderr
    """
    if isinstance(command, list) and shell:
        command = " ".join(command)
        
    cmd_str = command if isinstance(command, str) else " ".join(command)
    log(f"Ausführen: {cmd_str}", level="debug")
    
    try:
        result = subprocess.run(
            command,
            check=check,
            shell=shell,
            text=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None
        )
        
        if result.stdout and result.stdout.strip():
            logger.debug(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr and result.stderr.strip():
            logger.debug(f"STDERR:\n{result.stderr.strip()}")
            
        return result
    except subprocess.CalledProcessError as e:
        log(f"Befehl fehlgeschlagen: {cmd_str}", level="error")
        if e.stdout:
            logger.debug(f"STDOUT:\n{e.stdout.strip()}")
        if e.stderr:
            logger.debug(f"STDERR:\n{e.stderr.strip()}")
        raise

class RCONClient:
    """RCON-Client für die Kommunikation mit dem Minecraft-Server."""
    
    def __init__(self, host, port, password, timeout=5):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.mcr = None
        
    def connect(self):
        """Stellt eine Verbindung zum RCON-Server her."""
        try:
            log(f"Verbindung zum RCON-Server {self.host}:{self.port} wird hergestellt...", level="debug")
            self.mcr = mcrcon.MCRcon(self.host, self.password, port=self.port, timeout=self.timeout)
            self.mcr.connect()
            log(f"RCON-Verbindung hergestellt zu {self.host}:{self.port}", level="success")
            return True
        except Exception as e:
            log(f"RCON-Verbindung fehlgeschlagen: {e}", level="error")
            return False
            
    def disconnect(self):
        """Trennt die Verbindung zum RCON-Server."""
        if self.mcr:
            try:
                self.mcr.disconnect()
                log("RCON-Verbindung getrennt", level="debug")
            except Exception as e:
                log(f"Fehler beim Trennen der RCON-Verbindung: {e}", level="warning")
                
    def send_command(self, command):
        """
        Sendet einen Befehl an den Minecraft-Server über RCON.
        
        Args:
            command: Der zu sendende Minecraft-Befehl
            
        Returns:
            Die Antwort des Servers oder None bei Fehler
        """
        if not self.mcr:
            log("Nicht mit RCON verbunden", level="error")
            return None
            
        try:
            log(f"RCON-Befehl wird gesendet: {command}", level="debug")
            response = self.mcr.command(command)
            log(f"RCON-Antwort: {response}", level="debug")
            return response
        except Exception as e:
            log(f"RCON-Befehl fehlgeschlagen: {e}", level="error")
            return None
            
    def __enter__(self):
        """Kontextmanager-Support für 'with'-Statements."""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Trennt die Verbindung automatisch am Ende des 'with'-Blocks."""
        self.disconnect()

class MinecraftUpdater:
    """
    Hauptklasse für das Zero-Downtime-Update eines Minecraft-Servers in Kubernetes.
    """
    
    def __init__(self, args):
        self.minecraft_release = args.release
        self.namespace = args.namespace
        self.helm_chart_path = args.chart_path
        self.node_ip = args.node_ip
        self.rcon_port = args.rcon_port
        self.rcon_password = args.rcon_password
        self.update_timeout = args.timeout
        self.dry_run = args.dry_run
        
        # Init-Zeit für Logs und Backup-Benennung
        self.start_time = datetime.now()
        self.update_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # Tracking-Variablen für den Update-Status
        self.success = False
        self.rollback_needed = False
        self.current_step = 0
        self.total_steps = 10  # Gesamtzahl der Schritte im Update-Prozess
        
    def get_pod_name(self, index):
        """Gibt den Podnamen für den angegebenen Index zurück."""
        return f"{self.minecraft_release}-{index}"
        
    def wait_for_pod_ready(self, pod_name, timeout=180):
        """
        Wartet, bis ein Pod bereit ist.
        
        Args:
            pod_name: Name des Pods
            timeout: Timeout in Sekunden
            
        Returns:
            True, wenn der Pod bereit ist, False bei Timeout
        """
        log(f"Warte auf Bereitschaft von Pod {pod_name}...")
        
        if self.dry_run:
            log("[TROCKEN] Pod-Bereitschaft wird simuliert", level="warning")
            time.sleep(2)
            return True
            
        try:
            result = run_command([
                "kubectl", "wait", "--for=condition=ready", 
                f"pod/{pod_name}", f"--timeout={timeout}s",
                "-n", self.namespace
            ])
            log(f"Pod {pod_name} ist bereit", level="success")
            return True
        except subprocess.CalledProcessError:
            log(f"Timeout beim Warten auf Pod {pod_name}", level="error")
            return False
            
    def scale_statefulset(self, replicas):
        """
        Skaliert das StatefulSet auf die angegebene Anzahl von Replicas.
        
        Args:
            replicas: Anzahl der gewünschten Replicas
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Skaliere StatefulSet {self.minecraft_release} auf {replicas} Replicas...")
        
        if self.dry_run:
            log(f"[TROCKEN] StatefulSet würde auf {replicas} skaliert werden", level="warning")
            return True
            
        try:
            run_command([
                "kubectl", "scale", "statefulset", self.minecraft_release,
                f"--replicas={replicas}", "-n", self.namespace
            ])
            log(f"StatefulSet auf {replicas} skaliert", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Skalieren des StatefulSets: {e}", level="error")
            return False
            
    def upgrade_helm_release(self):
        """
        Führt ein Helm-Upgrade für das Minecraft-Release durch.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Führe Helm-Upgrade für Release {self.minecraft_release} durch...")
        
        if self.dry_run:
            log("[TROCKEN] Helm-Upgrade würde durchgeführt werden", level="warning")
            return True
            
        try:
            cmd = [
                "helm", "upgrade", self.minecraft_release, self.helm_chart_path,
                "--set", f"replicaCount=1", "-n", self.namespace
            ]
            run_command(cmd)
            log("Helm-Upgrade erfolgreich abgeschlossen", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Helm-Upgrade fehlgeschlagen: {e}", level="error")
            return False
            
    def sync_world_data(self, pod_name, direction):
        """
        Synchronisiert die Weltdaten zwischen einem Pod und dem Backup.
        
        Args:
            pod_name: Name des Pods
            direction: "to-backup" oder "from-backup"
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        cmd_desc = "zum Backup" if direction == "to-backup" else "vom Backup"
        log(f"Synchronisiere Weltdaten {cmd_desc} für Pod {pod_name}...")
        
        if self.dry_run:
            log(f"[TROCKEN] Weltsynchronisierung würde ausgeführt werden: {direction}", level="warning")
            return True
            
        try:
            result = run_command([
                "kubectl", "exec", "-i", pod_name, "-n", self.namespace, "--",
                "/bin/bash", "-c", f"/scripts/world-sync.sh {direction}"
            ])
            log(f"Weltsynchronisierung {cmd_desc} abgeschlossen", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Weltsynchronisierung fehlgeschlagen: {e}", level="error")
            return False
            
    def delete_pod(self, pod_name):
        """
        Löscht einen Pod, um einen Neustart zu erzwingen.
        
        Args:
            pod_name: Name des zu löschenden Pods
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Lösche Pod {pod_name} für Neustart...")
        
        if self.dry_run:
            log(f"[TROCKEN] Pod {pod_name} würde gelöscht werden", level="warning")
            return True
            
        try:
            run_command([
                "kubectl", "delete", "pod", pod_name, "-n", self.namespace
            ])
            log(f"Pod {pod_name} erfolgreich gelöscht", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Löschen des Pods: {e}", level="error")
            return False
            
    def notify_players(self, message):
        """
        Sendet eine Nachricht an alle Spieler über RCON.
        
        Args:
            message: Die zu sendende Nachricht
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.rcon_password:
            log("Kein RCON-Passwort angegeben, überspringe Spielerbenachrichtigung", level="warning")
            return False
            
        if self.dry_run:
            log(f"[TROCKEN] Würde Spieler benachrichtigen: {message}", level="warning")
            return True
            
        try:
            with RCONClient(self.node_ip, self.rcon_port, self.rcon_password) as rcon:
                if not rcon.mcr:
                    return False
                    
                # tellraw verwendet JSON für formatierte Nachrichten
                json_message = f'{{"text":"{message}","color":"gold","bold":true}}'
                command = f'tellraw @a {json_message}'
                result = rcon.send_command(command)
                
                # Server-weite Nachricht (erscheint auch in der Konsole)
                rcon.send_command(f'say {message}')
                
                log(f"Spielerbenachrichtigung gesendet: {message}", level="success")
                return True
        except Exception as e:
            log(f"Fehler bei der Spielerbenachrichtigung: {e}", level="error")
            return False
            
    def save_world(self):
        """
        Sendet den save-all flush Befehl an den Minecraft-Server.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.rcon_password:
            log("Kein RCON-Passwort angegeben, überspringe Weltenspeicherung", level="warning")
            return False
            
        if self.dry_run:
            log("[TROCKEN] Würde Welt speichern (save-all flush)", level="warning")
            return True
            
        try:
            with RCONClient(self.node_ip, self.rcon_port, self.rcon_password) as rcon:
                if not rcon.mcr:
                    return False
                    
                result = rcon.send_command("save-all flush")
                log("Weltdaten gespeichert (save-all flush)", level="success")
                return True
        except Exception as e:
            log(f"Fehler beim Speichern der Weltdaten: {e}", level="error")
            return False
            
    def get_online_players(self):
        """
        Ruft die Liste der online Spieler ab.
        
        Returns:
            Anzahl der Spieler oder None bei Fehler
        """
        if not self.rcon_password:
            log("Kein RCON-Passwort angegeben, überspringe Spieleranzahlermittlung", level="warning")
            return None
            
        if self.dry_run:
            log("[TROCKEN] Würde Online-Spieler abfragen", level="warning")
            return 0
            
        try:
            with RCONClient(self.node_ip, self.rcon_port, self.rcon_password) as rcon:
                if not rcon.mcr:
                    return None
                    
                result = rcon.send_command("list")
                if result:
                    # Typisches Format: "There are X of a maximum of Y players online: [names]"
                    parts = result.split(":")
                    if len(parts) > 0:
                        count_part = parts[0].split("are")[1].split("of")[0].strip()
                        try:
                            return int(count_part)
                        except ValueError:
                            log(f"Konnte Spieleranzahl nicht parsen: {result}", level="warning")
                
                return None
        except Exception as e:
            log(f"Fehler beim Abrufen der Online-Spieler: {e}", level="error")
            return None
            
    def update_progress(self, step_description):
        """Aktualisiert den Fortschritt des Update-Prozesses."""
        self.current_step += 1
        percentage = int((self.current_step / self.total_steps) * 100)
        log(f"SCHRITT {self.current_step}/{self.total_steps} ({percentage}%): {step_description}", level="info")
        
    def perform_update(self):
        """
        Führt den Zero-Downtime-Update-Prozess durch.
        
        Returns:
            True bei erfolgreicher Durchführung, False bei Fehler
        """
        log(f"=== MINECRAFT ZERO-DOWNTIME UPDATE GESTARTET ({self.update_id}) ===", level="info")
        log(f"Release: {self.minecraft_release}, Namespace: {self.namespace}", level="info")
        
        if self.dry_run:
            log("TROCKENLAUF-MODUS AKTIVIERT: Es werden keine tatsächlichen Änderungen vorgenommen!", level="warning")
        
        # Schritt 1: Status vor dem Update prüfen
        self.update_progress("Prüfe Serverstatus vor dem Update")
        player_count = self.get_online_players()
        if player_count is not None:
            log(f"Aktuell {player_count} Spieler online", level="info")
        
        # Schritt 2: Sicherstellen, dass Server 0 läuft
        self.update_progress("Stelle sicher, dass Server 0 läuft")
        if not self.scale_statefulset(1):
            log("Konnte nicht sicherstellen, dass Server 0 läuft", level="error")
            return False
            
        if not self.wait_for_pod_ready(self.get_pod_name(0), timeout=self.update_timeout):
            log("Server 0 wurde nicht bereit", level="error")
            return False
        
        # Schritt 3: Spieler benachrichtigen
        self.update_progress("Benachrichtige Spieler über bevorstehendes Update")
        self.notify_players("§6§lServer-Update wird vorbereitet. Keine Unterbrechung erforderlich!")
        
        # Schritt 4: Minecraft-Konfiguration aktualisieren
        self.update_progress("Aktualisiere Minecraft-Konfiguration mit Helm")
        if not self.upgrade_helm_release():
            log("Helm-Upgrade fehlgeschlagen", level="error")
            return False
        
        # Schritt 5: Weltdaten speichern und Spieler informieren
        self.update_progress("Speichere aktuelle Weltdaten")
        self.notify_players("§6§lWeltdaten werden gespeichert...")
        if not self.save_world():
            log("Konnte Weltdaten nicht speichern", level="warning")
            # Nicht kritisch, weitermachen
            
        time.sleep(3)  # Kurze Pause nach dem Speichern
        
        # Schritt 6: Weltdaten von Server 0 zu Backup synchronisieren
        self.update_progress("Synchronisiere Weltdaten von Server 0 zu Backup")
        self.notify_players("§6§lWeltdaten werden synchronisiert...")
        if not self.sync_world_data(self.get_pod_name(0), "to-backup"):
            log("Weltsynchronisierung zu Backup fehlgeschlagen", level="error")
            return False
            
        # Schritt 7: Starte Server 1 mit den Backup-Weltdaten
        self.update_progress("Starte zweiten Server mit Backup-Weltdaten")
        if not self.scale_statefulset(2):
            log("Skalierung auf 2 Replicas fehlgeschlagen", level="error")
            return False
            
        if not self.wait_for_pod_ready(self.get_pod_name(1), timeout=self.update_timeout):
            log("Server 1 wurde nicht bereit", level="error")
            # Trotzdem weitermachen, Server 0 aktualisieren
            
        # Schritt 8: Lade Weltdaten aus dem Backup auf Server 1
        self.update_progress("Lade Weltdaten aus Backup auf Server 1")
        if not self.sync_world_data(self.get_pod_name(1), "from-backup"):
            log("Weltsynchronisierung von Backup zu Server 1 fehlgeschlagen", level="warning")
            # Nicht kritisch, weitermachen
            
        self.notify_players("§6§lAlternativer Server ist bereit. Update wird fortgesetzt...")
        
        # Schritt 9: Server 0 neustarten
        self.update_progress("Starte Server 0 neu für Update")
        if not self.delete_pod(self.get_pod_name(0)):
            log("Konnte Server 0 nicht neustarten", level="error")
            # Trotzdem weitermachen
            
        if not self.wait_for_pod_ready(self.get_pod_name(0), timeout=self.update_timeout):
            log("Neugestarteter Server 0 wurde nicht bereit", level="error")
            self.rollback_needed = True
            # Trotzdem versuchen, Daten zu synchronisieren
            
        # Schritt 10: Weltdaten vom Backup zu Server 0 zurück synchronisieren
        self.update_progress("Synchronisiere Weltdaten vom Backup zurück zu Server 0")
        if not self.sync_world_data(self.get_pod_name(0), "from-backup"):
            log("Weltsynchronisierung vom Backup zu Server 0 fehlgeschlagen", level="error")
            self.rollback_needed = True
            
        # Schritt 11: Aufräumen - Server 1 herunterfahren, wenn Server 0 bereit ist
        self.update_progress("Räume auf: Fahre Server 1 herunter")
        
        # Vor dem Herunterfahren: Prüfen, ob Server 0 wirklich bereit ist
        if self.rollback_needed:
            log("Update fehlgeschlagen. Server 1 wird als Backup beibehalten.", level="warning")
            self.notify_players("§c§lUpdate fehlgeschlagen. Bitte kontaktieren Sie einen Administrator.")
        else:
            # Alles okay, Server 1 kann heruntergefahren werden
            self.notify_players("§a§lUpdate erfolgreich abgeschlossen!")
            if not self.scale_statefulset(1):
                log("Konnte nicht auf 1 Replica zurückskalieren", level="warning")
                # Nicht kritisch
        
        # Abschluss
        duration = (datetime.now() - self.start_time).total_seconds()
        if self.rollback_needed:
            log(f"=== UPDATE FEHLGESCHLAGEN (Dauer: {duration:.1f}s) ===", level="error")
            return False
        else:
            self.success = True
            log(f"=== UPDATE ERFOLGREICH ABGESCHLOSSEN (Dauer: {duration:.1f}s) ===", level="success")
            return True

def parse_arguments():
    """Parst die Kommandozeilenargumente."""
    parser = argparse.ArgumentParser(description="Minecraft Zero-Downtime Update Script")
    
    parser.add_argument("--release", default="minecraft-server",
                        help="Name des Helm-Releases (Standard: minecraft-server)")
    parser.add_argument("--namespace", default="default",
                        help="Kubernetes-Namespace (Standard: default)")
    parser.add_argument("--chart-path", default="./minecraft/",
                        help="Pfad zum Helm-Chart (Standard: ./minecraft/)")
    parser.add_argument("--node-ip", default="localhost",
                        help="IP-Adresse des Kubernetes-Nodes (für RCON)")
    parser.add_argument("--rcon-port", type=int, default=30575,
                        help="NodePort für RCON (Standard: 30575)")
    parser.add_argument("--rcon-password",
                        help="RCON-Passwort (optional, für Spielerbenachrichtigungen)")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Timeout in Sekunden für Podbereitschaft (Standard: 180)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulationsmodus ohne tatsächliche Änderungen")
    
    return parser.parse_args()

def main():
    """Hauptfunktion des Skripts."""
    print(f"\n{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}  MINECRAFT ZERO-DOWNTIME UPDATER  {Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}\n")
    
    args = parse_arguments()
    updater = MinecraftUpdater(args)
    
    try:
        success = updater.perform_update()
        if not success:
            log("Update nicht erfolgreich abgeschlossen. Siehe Logdatei für Details.", level="error")
            sys.exit(1)
    except KeyboardInterrupt:
        log("Update durch Benutzer abgebrochen", level="warning")
        sys.exit(130)
    except Exception as e:
        log(f"Unerwarteter Fehler: {e}", level="error")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
        
    log(f"Detailliertes Update-Protokoll wurde gespeichert unter: {LOG_PATH}", level="info")
    sys.exit(0)

if __name__ == "__main__":
    main()
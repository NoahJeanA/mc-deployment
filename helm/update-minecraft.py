#!/usr/bin/env python3
"""
Minecraft Zero-Downtime Update Script (Überarbeitete Version)

Dieses Skript führt ein sicheres Update des Minecraft-Servers in Kubernetes durch,
mit minimalem Downtime für die Spieler. Es implementiert eine verbesserte 
Synchronisierungsstrategie für Weltdaten und verwendet das BungeeCord Proxy für
die nahtlose Übergabe der Spieler zwischen Servern.

Voraussetzungen:
- kubectl muss im Pfad sein und konfiguriert sein
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

def run_command(command, check=True, shell=False, capture_output=True, timeout=None):
    """
    Führt einen Shell-Befehl aus und protokolliert Ausgabe.
    
    Args:
        command: Der auszuführende Befehl (Liste oder String)
        check: Wenn True, wird bei Fehler eine Exception ausgelöst
        shell: Wenn True, wird der Befehl in einer Shell ausgeführt
        capture_output: Wenn True, wird die Ausgabe zurückgegeben
        timeout: Timeout in Sekunden für den Befehl
        
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
            stderr=subprocess.PIPE if capture_output else None,
            timeout=timeout
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
    except subprocess.TimeoutExpired:
        log(f"Timeout beim Ausführen des Befehls: {cmd_str}", level="error")
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
        self.bungee_release = args.bungee_release
        self.update_timeout = args.timeout
        self.dry_run = args.dry_run
        self.force_restart = args.force_restart
        self.skip_validation = args.skip_validation
        
        # Init-Zeit für Logs und Backup-Benennung
        self.start_time = datetime.now()
        self.update_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # Tracking-Variablen für den Update-Status
        self.success = False
        self.rollback_needed = False
        self.current_step = 0
        self.total_steps = 12  # Gesamtzahl der Schritte im Update-Prozess
        
    def get_pod_name(self, index):
        """Gibt den Podnamen für den angegebenen Index zurück."""
        return f"{self.minecraft_release}-{index}"
    
    def get_bungee_pod_name(self):
        """Gibt den Podnamen des BungeeCord-Proxys zurück."""
        try:
            result = run_command([
                "kubectl", "get", "pods", "-l", f"app={self.bungee_release}",
                "-n", self.namespace, "-o", "jsonpath='{.items[0].metadata.name}'"
            ])
            return result.stdout.strip("'")
        except subprocess.CalledProcessError:
            log(f"Konnte BungeeCord Pod nicht finden", level="error")
            return f"{self.bungee_release}-0"  # Fallback
        
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
    
    def run_pod_script(self, pod_name, script_path, args):
        """
        Führt ein Script im angegebenen Pod aus.
        
        Args:
            pod_name: Name des Pods
            script_path: Pfad zum Script im Pod
            args: Argumente für das Script
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            result = run_command([
                "kubectl", "exec", "-i", pod_name, "-n", self.namespace, "--",
                "/bin/bash", "-c", f"{script_path} {args}"
            ])
            return True
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Ausführen des Scripts {script_path} mit Argumenten {args}: {e}", level="error")
            return False
    
    def run_bungee_command(self, command):
        """
        Führt einen Befehl im BungeeCord-Pod aus.
        
        Args:
            command: Der auszuführende Befehl
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        bungee_pod = self.get_bungee_pod_name()
        if not bungee_pod:
            log("Konnte keinen BungeeCord-Pod finden", level="error")
            return False
            
        try:
            result = run_command([
                "kubectl", "exec", "-i", bungee_pod, "-n", self.namespace, "--",
                "/bin/bash", "-c", f"echo '{command}' > /data/proxy_command"
            ])
            # Kurz warten, damit der Befehl verarbeitet werden kann
            time.sleep(1)
            return True
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Ausführen des BungeeCord-Befehls: {e}", level="error")
            return False
    
    def switch_bungee_priority(self, primary_server_index):
        """
        Ändert die Priorität im BungeeCord-Proxy.
        
        Args:
            primary_server_index: Index des primären Servers (0 oder 1)
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Ändere BungeeCord-Priorität zu Server {primary_server_index}...")
        
        if self.dry_run:
            log(f"[TROCKEN] BungeeCord-Priorität würde zu Server {primary_server_index} geändert werden", level="warning")
            return True
            
        bungee_pod = self.get_bungee_pod_name()
        if not bungee_pod:
            return False
            
        try:
            return self.run_pod_script(bungee_pod, "/scripts/bungee-script.sh", f"switch {primary_server_index}")
        except Exception as e:
            log(f"Fehler beim Ändern der BungeeCord-Priorität: {e}", level="error")
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
            ], timeout=600)  # 10-Minuten-Timeout für große Welten
            
            log(f"Weltsynchronisierung {cmd_desc} abgeschlossen", level="success")
            
            # Validierung nach Synchronisierung
            if not self.skip_validation:
                target = "backup" if direction == "to-backup" else "active"
                if not self.validate_world_data(pod_name, target):
                    log(f"Weltdatenvalidierung nach Synchronisierung fehlgeschlagen", level="error")
                    return False
            
            return True
        except subprocess.CalledProcessError as e:
            log(f"Weltsynchronisierung fehlgeschlagen: {e}", level="error")
            return False
        except subprocess.TimeoutExpired:
            log(f"Timeout bei der Weltsynchronisierung - die Welt könnte zu groß sein", level="error")
            return False
            
    def validate_world_data(self, pod_name, world_type="active"):
        """
        Validiert die Weltdaten in einem Pod.
        
        Args:
            pod_name: Name des Pods
            world_type: "active" oder "backup"
            
        Returns:
            True wenn die Weltdaten valide sind, False sonst
        """
        if self.skip_validation:
            log("Weltdatenvalidierung übersprungen", level="warning")
            return True
            
        log(f"Validiere {world_type} Weltdaten in Pod {pod_name}...", level="info")
        
        if self.dry_run:
            log(f"[TROCKEN] Weltdatenvalidierung würde durchgeführt werden", level="warning")
            return True
            
        try:
            result = run_command([
                "kubectl", "exec", "-i", pod_name, "-n", self.namespace, "--",
                "/bin/bash", "-c", f"/scripts/validate-world.sh {world_type}"
            ])
            
            if "Validierung erfolgreich abgeschlossen" in result.stdout:
                log(f"Weltdatenvalidierung erfolgreich", level="success")
                return True
            else:
                log(f"Weltdatenvalidierung fehlgeschlagen: {result.stdout}", level="error")
                return False
        except subprocess.CalledProcessError as e:
            log(f"Fehler bei der Weltdatenvalidierung: {e}", level="error")
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
            ], timeout=60)
            log(f"Pod {pod_name} erfolgreich gelöscht", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Löschen des Pods: {e}", level="error")
            return False
        except subprocess.TimeoutExpired:
            log(f"Timeout beim Löschen des Pods. Fortfahren...", level="warning")
            return True
    
    def shutdown_minecraft_server(self, pod_name):
        """
        Führt ein sauberes Herunterfahren des Minecraft-Servers durch.
        
        Args:
            pod_name: Name des Pods mit dem Minecraft-Server
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Fahre Minecraft-Server in Pod {pod_name} sauber herunter...")
        
        if self.dry_run:
            log(f"[TROCKEN] Server in {pod_name} würde sauber heruntergefahren werden", level="warning")
            return True
            
        # Bei erzwungenem Neustart direkt den Pod löschen
        if self.force_restart:
            log("Erzwungener Neustart aktiviert - Pod wird direkt gelöscht", level="warning")
            return self.delete_pod(pod_name)
            
        try:
            # Erst Spieler benachrichtigen
            with RCONClient(self.node_ip, self.rcon_port, self.rcon_password) as rcon:
                if rcon.mcr:
                    log("Benachrichtige Spieler über Serverstop...", level="info")
                    rcon.send_command("say §c§lServer wird für Update heruntergefahren in 10 Sekunden...")
                    time.sleep(5)
                    rcon.send_command("say §c§lServer wird für Update heruntergefahren in 5 Sekunden...")
                    time.sleep(5)
                    # Speichern der Welt erzwingen
                    log("Speichere Weltdaten...", level="info")
                    rcon.send_command("save-all flush")
                    time.sleep(3)
                    # Sauberen Stop senden
                    log("Sende Stop-Befehl an Server...", level="info")
                    rcon.send_command("stop")
                else:
                    log("RCON-Verbindung fehlgeschlagen, benutze alternativen Shutdown-Mechanismus", level="warning")
                    return self.delete_pod(pod_name)
                    
            # Warten bis der Server wirklich gestoppt ist - max 30 Sekunden
            log("Warte auf Server-Shutdown...", level="info")
            for i in range(30):
                try:
                    result = run_command([
                        "kubectl", "exec", "-i", pod_name, "-n", self.namespace, "--",
                        "/bin/sh", "-c", "pgrep -f 'java.*server.jar' || echo 'STOPPED'"
                    ], check=False)
                    
                    if "STOPPED" in result.stdout:
                        log(f"Minecraft-Server in {pod_name} erfolgreich heruntergefahren", level="success")
                        return True
                except Exception:
                    # Fehler ignorieren, vielleicht ist der Pod schon weg
                    pass
                    
                log(f"Server läuft noch, warte... ({i+1}/30)", level="debug")
                time.sleep(1)
                
            # Wenn der Server nicht reagiert, Pod löschen
            log(f"Server reagiert nicht auf Stop-Befehl. Erzwinge Neustart.", level="warning")
            return self.delete_pod(pod_name)
            
        except Exception as e:
            log(f"Fehler beim Herunterfahren: {e}", level="error")
            # Fallback zum Pod-Löschen
            return self.delete_pod(pod_name)
            
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
        
        # Schritt 3: Validiere die aktuelle Welt
        self.update_progress("Validiere Weltdaten vor dem Update")
        if not self.skip_validation:
            if not self.validate_world_data(self.get_pod_name(0), "active"):
                log("Weltdaten sind möglicherweise beschädigt. Fortfahren?", level="warning")
                if not self.force_restart:
                    log("Update abgebrochen. Verwenden Sie --force-restart, um trotzdem fortzufahren.", level="error")
                    return False
                log("Update wird erzwungen trotz möglicher Weltdatenbeschädigung", level="warning")
        
        # Schritt 4: Spieler benachrichtigen
        self.update_progress("Benachrichtige Spieler über bevorstehendes Update")
        self.notify_players("§6§lServer-Update wird vorbereitet. Update wird mit minimaler Unterbrechung durchgeführt.")
        
        # Schritt 5: Minecraft-Konfiguration aktualisieren
        self.update_progress("Aktualisiere Minecraft-Konfiguration mit Helm")
        if not self.upgrade_helm_release():
            log("Helm-Upgrade fehlgeschlagen", level="error")
            if not self.force_restart:
                return False
            log("Update wird trotz Helm-Upgrade-Fehler fortgesetzt", level="warning")
        
        # Schritt 6: Weltdaten speichern
        self.update_progress("Speichere aktuelle Weltdaten")
        self.notify_players("§6§lWeltdaten werden gespeichert...")
        if not self.save_world():
            log("Konnte Weltdaten nicht speichern", level="warning")
            # Nicht kritisch, weitermachen
            
        time.sleep(3)  # Kurze Pause nach dem Speichern
        
        # Schritt 7: Weltdaten zum Backup synchronisieren
        self.update_progress("Synchronisiere Weltdaten von Server 0 zu Backup")
        self.notify_players("§6§lWeltdaten werden synchronisiert...")
        if not self.sync_world_data(self.get_pod_name(0), "to-backup"):
            log("Weltsynchronisierung zu Backup fehlgeschlagen", level="error")
            if not self.force_restart:
                return False
            log("Update wird trotz Synchronisierungsfehler fortgesetzt", level="warning")
            
        # Schritt 8: Server 1 starten
        self.update_progress("Starte zweiten Server mit Backup-Weltdaten")
        if not self.scale_statefulset(2):
            log("Skalierung auf 2 Replicas fehlgeschlagen", level="error")
            if not self.force_restart:
                return False
            log("Update wird ohne zweiten Server fortgesetzt", level="warning")
        else:
            # Nur warten, wenn die Skalierung erfolgreich war
            if not self.wait_for_pod_ready(self.get_pod_name(1), timeout=self.update_timeout):
                log("Server 1 wurde nicht bereit", level="error")
                # Trotzdem weitermachen, Server 0 aktualisieren
            else:
                # Schritt 9: Weltdaten auf Server 1 synchronisieren
                self.update_progress("Lade Weltdaten aus Backup auf Server 1")
                if not self.sync_world_data(self.get_pod_name(1), "from-backup"):
                    log("Weltsynchronisierung von Backup zu Server 1 fehlgeschlagen", level="error")
                    # Nicht kritisch, weitermachen
                else:
                    # Wenn Server 1 bereit ist, ändere BungeeCord-Priorität
                    log("Ändere BungeeCord-Priorität zu Server 1...", level="info")
                    if self.switch_bungee_priority(1):
                        log("BungeeCord-Priorität erfolgreich geändert", level="success")
                    else:
                        log("Konnte BungeeCord-Priorität nicht ändern", level="warning")
        
        self.notify_players("§6§lAlternativer Server ist bereit. Update wird fortgesetzt...")
        
        # Schritt 10: Server 0 herunterfahren und neustarten
        self.update_progress("Fahre Server 0 herunter und starte ihn neu")
        if not self.shutdown_minecraft_server(self.get_pod_name(0)):
            log("Konnte Server 0 nicht herunterfahren", level="error")
            self.rollback_needed = True
            # Trotzdem weitermachen
            
        if not self.wait_for_pod_ready(self.get_pod_name(0), timeout=self.update_timeout):
            log("Neugestarteter Server 0 wurde nicht bereit", level="error")
            self.rollback_needed = True
            # Trotzdem versuchen, Daten zu synchronisieren
            
        # Schritt 11: Weltdaten zurück auf Server 0 synchronisieren
        self.update_progress("Synchronisiere Weltdaten vom Backup zurück zu Server 0")
        if not self.sync_world_data(self.get_pod_name(0), "from-backup"):
            log("Weltsynchronisierung vom Backup zu Server 0 fehlgeschlagen", level="error")
            self.rollback_needed = True
        
        # Priorität zurück zu Server 0 setzen
        log("Setze BungeeCord-Priorität zurück zu Server 0...", level="info")
        if self.switch_bungee_priority(0):
            log("BungeeCord-Priorität erfolgreich zurückgesetzt", level="success")
        else:
            log("Konnte BungeeCord-Priorität nicht zurücksetzen", level="warning")
            
        # Schritt 12: Aufräumen - Server 1 herunterfahren, wenn Server 0 bereit ist
        self.update_progress("Räume auf: Fahre Server 1 herunter")
        
        # Vor dem Herunterfahren: Prüfen, ob Server 0 wirklich bereit ist
        if self.rollback_needed:
            log("Update fehlgeschlagen. Server 1 wird als Backup beibehalten.", level="warning")
            self.notify_players("§c§lUpdate teilweise fehlgeschlagen. Ein Administrator wird benötigt.")
        else:
            # Alles okay, Server 1 kann heruntergefahren werden
            self.notify_players("§a§lUpdate erfolgreich abgeschlossen!")
            if not self.scale_statefulset(1):
                log("Konnte nicht auf 1 Replica zurückskalieren", level="warning")
                # Nicht kritisch
        
        # Abschluss
        duration = (datetime.now() - self.start_time).total_seconds()
        if self.rollback_needed:
            log(f"=== UPDATE TEILWEISE FEHLGESCHLAGEN (Dauer: {duration:.1f}s) ===", level="error")
            return False
        else:
            self.success = True
            log(f"=== UPDATE ERFOLGREICH ABGESCHLOSSEN (Dauer: {duration:.1f}s) ===", level="success")
            return True

def parse_arguments():
    """Parst die Kommandozeilenargumente."""
    parser = argparse.ArgumentParser(description="Minecraft Zero-Downtime Update Script (Verbesserte Version)")
    
    parser.add_argument("--release", default="minecraft-server",
                        help="Name des Minecraft Helm-Releases (Standard: minecraft-server)")
    parser.add_argument("--namespace", default="default",
                        help="Kubernetes-Namespace (Standard: default)")
    parser.add_argument("--chart-path", default="./minecraft/",
                        help="Pfad zum Helm-Chart (Standard: ./minecraft/)")
    parser.add_argument("--node-ip", default="localhost",
                        help="IP-Adresse des Kubernetes-Nodes (für RCON)")
    parser.add_argument("--rcon-port", type=int, default=30575,
                        help="NodePort für RCON (Standard: 30575)")
    parser.add_argument("--rcon-password", default="MeinSicheresRCONPasswort",
                        help="RCON-Passwort (Standard: MeinSicheresRCONPasswort)")
    parser.add_argument("--bungee-release", default="bungee",
                        help="Name des BungeeCord Helm-Releases (Standard: bungee)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Timeout in Sekunden für Podbereitschaft (Standard: 300)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulationsmodus ohne tatsächliche Änderungen")
    parser.add_argument("--force-restart", action="store_true",
                        help="Erzwinge Update auch bei Fehlern")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Überspringe Weltdatenvalidierung")
    
    return parser.parse_args()

def main():
    """Hauptfunktion des Skripts."""
    print(f"\n{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}  MINECRAFT ZERO-DOWNTIME UPDATER  {Style.RESET_ALL}")
    print(f"{Fore.CYAN}      VERBESSERTE VERSION 2.0      {Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}\n")
    
    args = parse_arguments()
    updater = MinecraftUpdater(args)
    
    try:
        success = updater.perform_update()
        if not success and not args.force_restart:
            log("Update nicht erfolgreich abgeschlossen. Siehe Logdatei für Details.", level="error")
            sys.exit(1)
        elif not success and args.force_restart:
            log("Update teilweise fehlgeschlagen, aber erzwungen abgeschlossen.", level="warning")
            sys.exit(0)
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
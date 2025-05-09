#!/usr/bin/env python3
"""
Minecraft Server Manager

Ein vereinfachtes Werkzeug zum Verwalten eines Minecraft-Servers in Kubernetes.
Funktionen:
- Sicheres Starten und Stoppen des Servers
- Spielerbenachrichtigungen
- Weltdaten-Backup vor jedem Neustart
- Helm-Updates anwenden

Voraussetzungen:
- kubectl im Pfad und konfiguriert
- helm im Pfad und konfiguriert
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
LOG_FILENAME = f"minecraft_manager_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
logger = logging.getLogger("minecraft-manager")

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

class MinecraftServerManager:
    """
    Hauptklasse für die Verwaltung des Minecraft-Servers in Kubernetes.
    """
    
    def __init__(self, args):
        self.minecraft_release = args.release
        self.namespace = args.namespace
        self.helm_chart_path = args.chart_path
        self.node_ip = args.node_ip
        self.rcon_port = args.rcon_port
        self.rcon_password = args.rcon_password
        self.timeout = args.timeout
        self.force = args.force
        self.action = args.action
        self.debug = args.debug
        self.update_helm = args.update_helm
        self.backup_world = args.backup_world
        self.start_wait_time = args.start_wait_time
        self.stop_wait_time = args.stop_wait_time
        
        # Helm Chart Pfad normalisieren
        self.helm_chart_path = self._find_helm_chart_path()
        log(f"Verwende Helm-Chart-Pfad: {self.helm_chart_path}", level="info")
        
        # Init-Zeit für Logs und Backup-Benennung
        self.start_time = datetime.now()
        self.operation_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        
    def _find_helm_chart_path(self):
        """Finde den korrekten Pfad zum Helm-Chart."""
        if os.path.exists(self.helm_chart_path):
            return self.helm_chart_path
            
        # Verschiedene relative Pfade ausprobieren
        possible_paths = [
            os.path.join(os.getcwd(), self.helm_chart_path),
            os.path.join(os.getcwd(), "helm", "minecraft"),
            os.path.join(os.getcwd(), "minecraft"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "minecraft"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "minecraft")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        log(f"WARNUNG: Helm-Chart-Pfad '{self.helm_chart_path}' nicht gefunden. Verwende Standardwert.", level="warning")
        return "minecraft"  # Standardwert zurückgeben
        
    def is_server_running(self):
        """
        Überprüft, ob der Minecraft-Server läuft.
        
        Returns:
            True, wenn der Server läuft, False sonst
        """
        try:
            result = run_command([
                "kubectl", "get", "statefulset", self.minecraft_release, 
                "-n", self.namespace, "-o", "jsonpath='{.spec.replicas}'"
            ])
            replicas = int(result.stdout.strip("'"))
            return replicas > 0
        except Exception as e:
            log(f"Fehler beim Überprüfen des Serverstatus: {e}", level="error")
            return False
            
    def get_pod_name(self):
        """Gibt den Namen des aktiven Minecraft Pods zurück, wenn vorhanden."""
        try:
            result = run_command([
                "kubectl", "get", "pods", "-l", f"app={self.minecraft_release}",
                "-n", self.namespace, "-o", "jsonpath='{.items[0].metadata.name}'"
            ], check=False)
            
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip("'")
            return None
        except Exception:
            return None
            
    def is_pod_ready(self, pod_name):
        """
        Überprüft, ob ein Pod bereit ist.
        
        Args:
            pod_name: Name des Pods
            
        Returns:
            True, wenn der Pod bereit ist, False sonst
        """
        try:
            result = run_command([
                "kubectl", "get", "pod", pod_name, "-n", self.namespace,
                "-o", "jsonpath='{.status.containerStatuses[0].ready}'"
            ], check=False)
            
            if result.returncode == 0 and result.stdout.strip("'") == "true":
                return True
            return False
        except Exception:
            return False
            
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
            
    def scale_server(self, replicas):
        """
        Skaliert den Minecraft-Server auf die angegebene Anzahl von Replicas.
        
        Args:
            replicas: Anzahl der gewünschten Replicas (0 oder 1)
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if replicas not in [0, 1]:
            log(f"Ungültige Replica-Anzahl: {replicas}. Nur 0 oder 1 sind erlaubt.", level="error")
            return False
            
        action = "ausschalten" if replicas == 0 else "einschalten"
        log(f"Minecraft-Server wird {action}...")
        
        try:
            run_command([
                "kubectl", "scale", "statefulset", self.minecraft_release,
                f"--replicas={replicas}", "-n", self.namespace
            ])
            log(f"StatefulSet wurde auf {replicas} Replica(s) skaliert", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Skalieren des StatefulSets: {e}", level="error")
            return False
            
    def update_helm_chart(self):
        """
        Führt ein Helm-Upgrade für den Minecraft-Server durch.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Führe Helm-Upgrade für Release {self.minecraft_release} durch...")
        
        try:
            # Überprüfe, ob der Pfad existiert
            if not os.path.exists(self.helm_chart_path):
                log(f"Helm-Chart-Pfad nicht gefunden: {self.helm_chart_path}", level="error")
                return False
                
            cmd = [
                "helm", "upgrade", self.minecraft_release, self.helm_chart_path,
                "-n", self.namespace
            ]
            
            result = run_command(cmd)
            log("Helm-Upgrade erfolgreich abgeschlossen", level="success")
            return True
        except subprocess.CalledProcessError as e:
            log(f"Helm-Upgrade fehlgeschlagen: {e}", level="error")
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
            
        try:
            with RCONClient(self.node_ip, self.rcon_port, self.rcon_password) as rcon:
                if not rcon.mcr:
                    return False
                    
                # tellraw verwendet JSON für formatierte Nachrichten
                json_message = f'{{"text":"{message}","color":"gold","bold":true}}'
                command = f'tellraw @a {json_message}'
                rcon.send_command(command)
                
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
            Anzahl der Spieler und Spielernamen, oder (None, None) bei Fehler
        """
        if not self.rcon_password:
            log("Kein RCON-Passwort angegeben, überspringe Spieleranzahlermittlung", level="warning")
            return None, None
            
        try:
            with RCONClient(self.node_ip, self.rcon_port, self.rcon_password) as rcon:
                if not rcon.mcr:
                    return None, None
                    
                result = rcon.send_command("list")
                if result:
                    # Typisches Format: "There are X of a maximum of Y players online: [names]"
                    parts = result.split(":")
                    if len(parts) >= 2:
                        count_part = parts[0].split("are")[1].split("of")[0].strip()
                        names_part = parts[1].strip()
                        try:
                            count = int(count_part)
                            return count, names_part
                        except ValueError:
                            log(f"Konnte Spieleranzahl nicht parsen: {result}", level="warning")
                
                return None, None
        except Exception as e:
            log(f"Fehler beim Abrufen der Online-Spieler: {e}", level="error")
            return None, None
    
    def run_pod_command(self, pod_name, command):
        """
        Führt einen Shell-Befehl im angegebenen Pod aus.
        
        Args:
            pod_name: Name des Pods
            command: Der auszuführende Befehl
            
        Returns:
            CompletedProcess-Objekt oder None bei Fehler
        """
        try:
            result = run_command([
                "kubectl", "exec", "-i", pod_name, "-n", self.namespace, "--",
                "/bin/sh", "-c", command
            ])
            return result
        except subprocess.CalledProcessError as e:
            log(f"Fehler beim Ausführen des Befehls '{command}' im Pod {pod_name}: {e}", level="error")
            return None

    def backup_server_world(self, pod_name):
        """
        Erstellt ein Backup der Minecraft-Weltdaten im Pod.
        
        Args:
            pod_name: Name des Pods
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log(f"Erstelle Backup der Weltdaten in Pod {pod_name}...")
        
        # Weltname ermitteln
        try:
            result = self.run_pod_command(
                pod_name, 
                "grep 'level-name=' /config/server.properties 2>/dev/null | cut -d'=' -f2 || echo 'world'"
            )
            
            if not result:
                world_name = "world"  # Standardwert
            else:
                world_name = result.stdout.strip()
                
            log(f"Weltname erkannt: {world_name}", level="info")
            
            # Erst Welt speichern via RCON
            self.save_world()
            
            # Backup erstellen
            backup_path = f"/backup-world/backups/{world_name}_{self.operation_id}.tar.gz"
            backup_cmd = f"mkdir -p /backup-world/backups && tar -czf {backup_path} -C /minecraft-world {world_name}"
            backup_result = self.run_pod_command(pod_name, backup_cmd)
            
            if backup_result:
                log(f"Weltdaten-Backup erstellt: {backup_path}", level="success")
                return True
            else:
                log("Fehler beim Erstellen des Weltdaten-Backups", level="error")
                return False
                
        except Exception as e:
            log(f"Fehler beim Backup der Weltdaten: {e}", level="error")
            return False
            
    def start_server(self):
        """
        Startet den Minecraft-Server.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log("=== MINECRAFT SERVER WIRD GESTARTET ===", level="info")
        
        # Überprüfen, ob der Server bereits läuft
        if self.is_server_running():
            pod_name = self.get_pod_name()
            if pod_name and self.is_pod_ready(pod_name):
                log("Minecraft-Server läuft bereits und ist bereit", level="info")
                return True
            elif pod_name:
                log("Minecraft-Server startet bereits, warte auf Bereitschaft...", level="info")
                return self.wait_for_pod_ready(pod_name, timeout=self.timeout)
            else:
                log("Minecraft-Server sollte laufen, aber kein Pod gefunden", level="warning")
        
        # Server starten
        if not self.scale_server(1):
            log("Fehler beim Starten des Minecraft-Servers", level="error")
            return False
            
        # Auf Pod warten
        time.sleep(5)  # Kurze Verzögerung, um sicherzustellen, dass der Pod erstellt wird
        
        pod_name = self.get_pod_name()
        if not pod_name:
            log("Konnte keinen Minecraft-Pod finden", level="error")
            return False
            
        # Auf Bereitschaft warten
        if not self.wait_for_pod_ready(pod_name, timeout=self.timeout):
            log("Server-Pod wurde nicht rechtzeitig bereit", level="error")
            return False
            
        log(f"Warte weitere {self.start_wait_time} Sekunden, um sicherzustellen, dass der Server vollständig gestartet ist...")
        time.sleep(self.start_wait_time)
        
        # Status überprüfen
        player_count, player_names = self.get_online_players()
        if player_count is not None:
            log(f"Server gestartet und bereit. Aktuell {player_count} Spieler online.", level="success")
            if player_count > 0:
                log(f"Online-Spieler: {player_names}", level="info")
        else:
            log("Server gestartet, aber RCON-Verbindung fehlgeschlagen", level="warning")
            
        return True
        
    def stop_server(self):
        """
        Stoppt den Minecraft-Server.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log("=== MINECRAFT SERVER WIRD GESTOPPT ===", level="info")
        
        # Überprüfen, ob der Server läuft
        if not self.is_server_running():
            log("Minecraft-Server ist bereits gestoppt", level="info")
            return True
            
        # Pod-Name abrufen
        pod_name = self.get_pod_name()
        if not pod_name:
            log("Kein laufender Minecraft-Pod gefunden", level="warning")
            # Trotzdem versuchen zu stoppen
        else:
            # Spieler benachrichtigen
            online_players, names = self.get_online_players()
            if online_players and online_players > 0:
                log(f"Es sind aktuell {online_players} Spieler online: {names}", level="warning")
                if not self.force:
                    confirm = input("Möchten Sie den Server trotzdem stoppen? (j/n): ")
                    if confirm.lower() != 'j':
                        log("Serverabschaltung abgebrochen", level="info")
                        return False
            
            # Spieler benachrichtigen
            self.notify_players("§c§lServer wird in 30 Sekunden heruntergefahren!")
            
            # Backup der Weltdaten erstellen, wenn gewünscht
            if self.backup_world:
                self.backup_server_world(pod_name)
            
            # Spieler benachrichtigen
            self.notify_players("§c§lServer wird in 20 Sekunden heruntergefahren!")
            
            time.sleep(10)
            
            # Spieler benachrichtigen
            self.notify_players("§c§lServer wird in 10 Sekunden heruntergefahren!")
            
            time.sleep(5)
            
            # Spieler benachrichtigen
            self.notify_players("§c§lServer wird in 5 Sekunden heruntergefahren!")
            
            time.sleep(5)
            
            # Welt speichern
            log("Speichere Weltdaten vor dem Herunterfahren...", level="info")
            self.save_world()
        
        # Warte kurz, damit die Weltdaten gespeichert werden können
        time.sleep(2)
        
        # Server stoppen durch Skalierung auf 0
        if not self.scale_server(0):
            log("Fehler beim Stoppen des Minecraft-Servers", level="error")
            return False
            
        log(f"Warte {self.stop_wait_time} Sekunden, bis der Server vollständig heruntergefahren ist...")
        time.sleep(self.stop_wait_time)
        
        log("Minecraft-Server wurde erfolgreich gestoppt", level="success")
        return True
        
    def restart_server(self):
        """
        Startet den Minecraft-Server neu.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        log("=== MINECRAFT SERVER WIRD NEU GESTARTET ===", level="info")
        
        # Überprüfen, ob eine Helm-Aktualisierung durchgeführt werden soll
        if self.update_helm:
            log("Helm-Chart wird vor dem Neustart aktualisiert...")
            if not self.update_helm_chart():
                if not self.force:
                    log("Helm-Update fehlgeschlagen, Neustart abgebrochen", level="error")
                    return False
                log("Helm-Update fehlgeschlagen, Neustart wird fortgesetzt (--force)", level="warning")
        
        # Server stoppen
        if not self.stop_server():
            log("Fehler beim Stoppen des Servers", level="error")
            return False
            
        # Kurze Pause
        log("Warte 10 Sekunden, bevor der Server wieder gestartet wird...", level="info")
        time.sleep(10)
        
        # Server starten
        if not self.start_server():
            log("Fehler beim Starten des Servers", level="error")
            return False
            
        log("Minecraft-Server wurde erfolgreich neu gestartet", level="success")
        return True
        
    def server_status(self):
        """
        Gibt den aktuellen Status des Minecraft-Servers aus.
        
        Returns:
            True, wenn Server läuft, False sonst
        """
        log("=== MINECRAFT SERVER STATUS ===", level="info")
        
        # Überprüfen, ob der Server läuft
        server_running = self.is_server_running()
        
        if server_running:
            pod_name = self.get_pod_name()
            if pod_name:
                log(f"Server-Pod: {pod_name}", level="info")
                
                # Überprüfe Pod-Bereitschaft
                if self.is_pod_ready(pod_name):
                    log("Server-Status: BEREIT", level="success")
                    
                    # Server-Informationen abrufen
                    player_count, player_names = self.get_online_players()
                    if player_count is not None:
                        log(f"Online-Spieler: {player_count}", level="info")
                        if player_count > 0:
                            log(f"Spielernamen: {player_names}", level="info")
                    
                    # Detaillierte Informationen, wenn Debug aktiviert ist
                    if self.debug:
                        try:
                            # Pod-Details abrufen
                            pod_info = run_command([
                                "kubectl", "get", "pod", pod_name, "-n", self.namespace, "-o", "json"
                            ])
                            
                            if pod_info:
                                log("=== POD DETAILS ===", level="debug")
                                log(pod_info.stdout, level="debug")
                                
                            # Logs abrufen
                            pod_logs = run_command([
                                "kubectl", "logs", pod_name, "-n", self.namespace, "--tail=20"
                            ])
                            
                            if pod_logs:
                                log("=== LETZTE 20 LOG-ZEILEN ===", level="debug")
                                log(pod_logs.stdout, level="debug")
                                
                        except Exception as e:
                            log(f"Fehler beim Abrufen der Debug-Informationen: {e}", level="error")
                else:
                    log("Server-Status: STARTET", level="warning")
            else:
                log("Server-Status: UNBEKANNT (Kein Pod gefunden, obwohl StatefulSet > 0)", level="warning")
        else:
            log("Server-Status: GESTOPPT", level="info")
            
        return server_running

    def execute_action(self):
        """
        Führt die angegebene Aktion aus.
        
        Returns:
            0 bei Erfolg, 1 bei Fehler
        """
        if self.action == "start":
            success = self.start_server()
        elif self.action == "stop":
            success = self.stop_server()
        elif self.action == "restart":
            success = self.restart_server()
        elif self.action == "status":
            success = True  # Status-Abfrage kann nicht fehlschlagen
            self.server_status()
        elif self.action == "backup":
            pod_name = self.get_pod_name()
            if not pod_name:
                log("Kein laufender Minecraft-Pod gefunden, Backup nicht möglich", level="error")
                success = False
            else:
                success = self.backup_server_world(pod_name)
        else:
            log(f"Unbekannte Aktion: {self.action}", level="error")
            success = False
            
        return 0 if success else 1

def parse_arguments():
    """Parst die Kommandozeilenargumente."""
    parser = argparse.ArgumentParser(description="Minecraft Server Manager")
    
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "backup"],
                        help="Aktion, die ausgeführt werden soll")
    
    parser.add_argument("--release", default="minecraft-server",
                        help="Name des Minecraft Helm-Releases (Standard: minecraft-server)")
    parser.add_argument("--namespace", default="default",
                        help="Kubernetes-Namespace (Standard: default)")
    parser.add_argument("--chart-path", default="minecraft",
                        help="Pfad zum Helm-Chart (Standard: minecraft)")
    parser.add_argument("--node-ip", default="localhost",
                        help="IP-Adresse des Kubernetes-Nodes (für RCON)")
    parser.add_argument("--rcon-port", type=int, default=30575,
                        help="NodePort für RCON (Standard: 30575)")
    parser.add_argument("--rcon-password", default="MeinSicheresRCONPasswort",
                        help="RCON-Passwort (Standard: MeinSicheresRCONPasswort)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Timeout in Sekunden für Podbereitschaft (Standard: 300)")
    parser.add_argument("--force", action="store_true",
                        help="Aktionen erzwingen, auch wenn Fehler auftreten")
    parser.add_argument("--debug", action="store_true",
                        help="Debug-Informationen anzeigen")
    parser.add_argument("--update-helm", action="store_true",
                        help="Helm-Chart aktualisieren (nur bei restart)")
    parser.add_argument("--backup-world", action="store_true",
                        help="Welt-Backup erstellen (nur bei stop/restart)")
    parser.add_argument("--start-wait-time", type=int, default=20,
                        help="Wartezeit nach dem Start des Servers (Standard: 20 Sekunden)")
    parser.add_argument("--stop-wait-time", type=int, default=10,
                        help="Wartezeit nach dem Stoppen des Servers (Standard: 10 Sekunden)")
    
    return parser.parse_args()

def main():
    """Hauptfunktion des Skripts."""
    print(f"\n{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}      MINECRAFT SERVER MANAGER       {Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}\n")
    
    args = parse_arguments()
    manager = MinecraftServerManager(args)
    
    try:
        exit_code = manager.execute_action()
        
        # Log-Informationen
        if exit_code == 0:
            log(f"Operation '{args.action}' erfolgreich abgeschlossen.", level="success")
        else:
            log(f"Operation '{args.action}' mit Fehlern abgeschlossen.", level="error")
            
        log(f"Detailliertes Protokoll wurde gespeichert unter: {LOG_PATH}", level="info")
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        log("Operation durch Benutzer abgebrochen", level="warning")
        sys.exit(130)
    except Exception as e:
        log(f"Unerwarteter Fehler: {e}", level="error")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
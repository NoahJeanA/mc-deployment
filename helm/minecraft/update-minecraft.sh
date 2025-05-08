#!/bin/bash
# zero-downtime-update.sh - Verbessertes Skript für Zero-Downtime-Updates mit BungeeCord

# Konfiguration
MINECRAFT_RELEASE="minecraft-server"
BUNGEE_RELEASE="bungee"
NAMESPACE="default"

# Farben für Ausgabe
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Zero-Downtime Minecraft Update...${NC}"

# 1. Sicherstellen, dass Server 0 läuft und Server 1 gestoppt ist
echo -e "${YELLOW}Ensuring server 0 is running and server 1 is stopped...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=1
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-0 --timeout=180s

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to ensure server 0 is running. Aborting.${NC}"
    exit 1
fi

# 2. Prüfen, ob Spieler verbunden sind
echo -e "${YELLOW}Checking for connected players...${NC}"
PLAYERS=$(kubectl exec -i ${MINECRAFT_RELEASE}-0 -- /bin/bash -c "cd /app && java -cp server.jar org.bukkit.craftbukkit.Main list | grep 'players online'" || echo "No players")
echo -e "Player status: ${GREEN}${PLAYERS}${NC}"

# 3. Konfiguration aktualisieren (wird später wirksam)
echo -e "${YELLOW}Updating Minecraft configuration...${NC}"
helm upgrade ${MINECRAFT_RELEASE} ./minecraft/ --set replicaCount=1

# 4. Weltdaten von Server 0 zu Backup synchronisieren
echo -e "${YELLOW}Syncing world data from server 0 to backup...${NC}"
kubectl exec -i ${MINECRAFT_RELEASE}-0 -- /bin/bash -c "/scripts/world-sync.sh to-backup"

# 5. Starte Server 1 mit den Backup-Weltdaten
echo -e "${YELLOW}Starting server 1 with backup world data...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=2
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-1 --timeout=180s

# 6. Benachrichtigung an Spieler senden
echo -e "${YELLOW}Notifying players about server update...${NC}"
kubectl exec -i deployment/${BUNGEE_RELEASE} -- rcon-cli alert "Server-Update wird vorbereitet. Ihr werdet automatisch zum anderen Server umgeleitet."

# 7. Spieler zum Server 2 umleiten
echo -e "${YELLOW}Redirecting players to server2...${NC}"
kubectl exec -i deployment/${BUNGEE_RELEASE} -- rcon-cli send all server2
sleep 5

# 8. Server 0 neustarten
echo -e "${YELLOW}Stopping server 0 for update...${NC}"
kubectl delete pod ${MINECRAFT_RELEASE}-0
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-0 --timeout=180s

# 9. Weltdaten vom Backup zu Server 0 zurück synchronisieren
echo -e "${YELLOW}Syncing world data from backup to server 0...${NC}"
kubectl exec -i ${MINECRAFT_RELEASE}-0 -- /bin/bash -c "/scripts/world-sync.sh from-backup"

# 10. Spieler zurück zu Server 0 umleiten
echo -e "${YELLOW}Redirecting players back to server1...${NC}"
kubectl exec -i deployment/${BUNGEE_RELEASE} -- rcon-cli alert "Update abgeschlossen. Ihr werdet zum aktualisierten Server zurückgeleitet."
kubectl exec -i deployment/${BUNGEE_RELEASE} -- rcon-cli send all server1
sleep 5

# 11. Server 1 herunterfahren, um Session.lock-Konflikte zu vermeiden
echo -e "${YELLOW}Shutting down server 1...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=1

echo -e "${GREEN}Zero-Downtime Update completed successfully!${NC}"